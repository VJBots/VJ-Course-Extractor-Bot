import asyncio
import json
import logging
import os
import time
import uuid
import zipfile
from typing import Any, Dict, List, Optional
import aiohttp
from pyrogram import Client, filters
from pyrogram.types import Message

from helpers import ask_user, extract_url_from_video_details, is_authorized


# Throttle API requests to prevent Penpencil rate-limiting / silent failure
SEMAPHORE = asyncio.Semaphore(10)


class ProcessCancelledException(Exception):
    """Custom exception raised when a process is cancelled by the user."""
    pass


def format_time(seconds: float) -> str:
    """Format seconds into a human-readable HH:MM:SS or MM:SS string."""
    seconds = int(seconds)
    mins, secs = divmod(seconds, 60)
    hrs, mins = divmod(mins, 60)
    if hrs > 0:
        return f"{hrs:02d}h {mins:02d}m {secs:02d}s"
    return f"{mins:02d}m {secs:02d}s"


async def prompt_user(bot: Client, message: Message, editable: Message, text: str, user_id: int) -> str:
    """Helper wrapper to ask user input with built-in /cancel check."""
    cancel_notice = "\n\n<blockquote>❌ **Send `/cancel` at any time to abort this process.**</blockquote>"
    full_text = text + cancel_notice
    
    response = await ask_user(bot, message, editable, full_text, user_id)
    
    if response is None or response.strip().lower() == "/cancel":
        await editable.edit("**Process Cancelled by User ❌**")
        raise ProcessCancelledException("User requested cancellation.")
    
    return response.strip()


async def update_status_card(editable: Message, task_name: str, current: int, total: int, start_time: float, activity: str):
    """Formats and updates a progress tracking message card."""
    percentage = (current / total * 100) if total > 0 else 0
    elapsed = time.time() - start_time
    
    if current > 0 and total > 0:
        avg_time_per_unit = elapsed / current
        remaining_units = total - current
        eta = avg_time_per_unit * remaining_units
        eta_str = format_time(eta)
    else:
        eta_str = "Calculating..."

    # Create a 10-block progress bar
    filled_blocks = int(percentage // 10)
    progress_bar = "▓" * filled_blocks + "░" * (10 - filled_blocks)

    status_text = (
        f"<blockquote>⚙️ **Processing Task:** `{task_name}`</blockquote>\n\n"
        f"📊 **Progress:** [{progress_bar}] `{percentage:.1f}%` ({current}/{total})\n"
        f"📌 **Current Activity:** {activity}\n"
        f"⏱️ **Time Elapsed:** `{format_time(elapsed)}`\n"
        f"⏳ **Time Left (ETA):** `{eta_str}`\n\n"
        f"<blockquote>❌ **Send `/cancel` to abort.**</blockquote>"
    )
    
    try:
        await editable.edit(status_text)
    except Exception:
        pass


async def fetch_pwwp_data(session: aiohttp.ClientSession, url: str, headers: Dict = None, params: Dict = None, data: Dict = None, method: str = "GET") -> Any:
    async with SEMAPHORE:
        for attempt in range(3):
            try:
                async with session.request(method, url, headers=headers, params=params, json=data) as response:
                    response.raise_for_status()
                    return await response.json()
            except aiohttp.ClientError as e:
                logging.error(f"PWWP Attempt {attempt + 1} failed for {url}: {e}")
            except Exception as e:
                logging.exception(f"PWWP Unexpected error for {url}: {e}")
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)
        return None


async def process_pwwp_chapter_content(session: aiohttp.ClientSession, selected_batch_id: str, subject_id: str, schedule_id: str, content_type: str, headers: Dict) -> Dict[str, List[str]]:
    url = f"https://api.penpencil.co/v1/batches/{selected_batch_id}/subject/{subject_id}/schedule/{schedule_id}/schedule-details"
    data = await fetch_pwwp_data(session, url, headers=headers)
    content = []

    if data and data.get("success") and data.get("data"):
        item = data["data"]
        topic = item.get("topic", "")

        if content_type in ("videos", "DppVideos"):
            video_url = extract_url_from_video_details(item)
            if video_url:
                content.append(f"{topic}:{video_url}")
            else:
                for hw in item.get("homeworkIds", []) or []:
                    hw_topic = hw.get("topic", topic)
                    for att in hw.get("attachmentIds", []) or []:
                        u = att.get("baseUrl", "") + att.get("key", "")
                        if u and not u.endswith(".pdf"):
                            content.append(f"{hw_topic}:{u}")

        elif content_type in ("notes", "DppNotes"):
            for hw in item.get("homeworkIds", []) or []:
                hw_topic = hw.get("topic", topic)
                for att in hw.get("attachmentIds", []) or []:
                    u = att.get("baseUrl", "") + att.get("key", "")
                    if u:
                        content.append(f"{hw_topic}:{u}")

    return {content_type: content} if content else {}


async def fetch_pwwp_all_schedule(session: aiohttp.ClientSession, chapter_id: str, selected_batch_id: str, subject_id: str, content_type: str, headers: Dict) -> List[Dict]:
    all_schedules, page = [], 1
    while True:
        url = f"https://api.penpencil.co/v2/batches/{selected_batch_id}/subject/{subject_id}/contents"
        params = {"tag": chapter_id, "contentType": content_type, "page": page}
        data = await fetch_pwwp_data(session, url, headers=headers, params=params)

        if data and data.get("success") and data.get("data"):
            for item in data["data"]:
                item["content_type"] = content_type
                if content_type in ("videos", "DppVideos"):
                    direct_url = extract_url_from_video_details(item)
                    if direct_url:
                        item["_pre_extracted_url"] = direct_url
                all_schedules.append(item)
            page += 1
        else:
            break
    return all_schedules


async def process_pwwp_chapters(session: aiohttp.ClientSession, chapter_id: str, selected_batch_id: str, subject_id: str, headers: Dict) -> Dict[str, List[str]]:
    content_types = ["videos", "notes", "DppNotes", "DppVideos"]
    all_schedules = await asyncio.gather(*[fetch_pwwp_all_schedule(session, chapter_id, selected_batch_id, subject_id, ct, headers) for ct in content_types])
    
    flat_schedule = [s for sublist in all_schedules for s in sublist]
    tasks = []
    
    for item in flat_schedule:
        sid, ct = item["_id"], item["content_type"]
        if ct in ("videos", "DppVideos") and item.get("_pre_extracted_url"):
            async def _direct(c_type=ct, name=item.get("topic", sid), url=item["_pre_extracted_url"]):
                return {c_type: [f"{name}:{url}"]}
            tasks.append(_direct())
        else:
            tasks.append(process_pwwp_chapter_content(session, selected_batch_id, subject_id, sid, ct, headers))

    results = await asyncio.gather(*tasks)
    combined = {}
    for res in results:
        for c_type, c_list in res.items():
            combined.setdefault(c_type, []).extend(c_list)
    return combined


async def get_pwwp_all_chapters(session: aiohttp.ClientSession, selected_batch_id: str, subject_id: str, headers: Dict) -> List[Dict]:
    chapters, page = [], 1
    while True:
        url = f"https://api.penpencil.co/v2/batches/{selected_batch_id}/subject/{subject_id}/topics?page={page}"
        data = await fetch_pwwp_data(session, url, headers=headers)
        if data and data.get("data"):
            chapters.extend(data["data"])
            page += 1
        else:
            break
    return chapters


async def process_pwwp_subject(session: aiohttp.ClientSession, subject: Dict, selected_batch_id: str, selected_batch_name: str, zipf: zipfile.ZipFile, json_data: Dict, all_subject_urls: Dict[str, List[str]], headers: Dict):
    subject_name = subject.get("subject", "Unknown Subject").replace("/", "-")
    subject_id = subject.get("_id")
    json_data[selected_batch_name][subject_name] = {}
    zipf.writestr(f"{subject_name}/", "")

    chapters = await get_pwwp_all_chapters(session, selected_batch_id, subject_id, headers)
    results = await asyncio.gather(*[process_pwwp_chapters(session, ch["_id"], selected_batch_id, subject_id, headers) for ch in chapters])

    all_urls = []
    for ch, content_map in zip(chapters, results):
        ch_name = ch.get("name", "Unknown Chapter").replace("/", "-")
        json_data[selected_batch_name][subject_name][ch_name] = {}
        for c_type in ["videos", "notes", "DppNotes", "DppVideos"]:
            if content_map.get(c_type):
                c_list = content_map[c_type]
                c_list.reverse()
                zipf.writestr(f"{subject_name}/{ch_name}/{c_type}.txt", "\n".join(c_list).encode("utf-8"))
                json_data[selected_batch_name][subject_name][ch_name][c_type] = c_list
                all_urls.extend(c_list)
    all_subject_urls[subject_name] = all_urls


async def get_pwwp_todays_schedule_content_details(session: aiohttp.ClientSession, selected_batch_id: str, subject_id: str, schedule_id: str, headers: Dict) -> List[str]:
    url = f"https://api.penpencil.co/v1/batches/{selected_batch_id}/subject/{subject_id}/schedule/{schedule_id}/schedule-details"
    data = await fetch_pwwp_data(session, url, headers=headers)
    content = []
    if data and data.get("success") and data.get("data"):
        item = data["data"]
        name = item.get("topic", "")
        v_url = extract_url_from_video_details(item)
        if v_url:
            content.append(f"{name}:{v_url}\n")
        else:
            for hw in item.get("homeworkIds", []) or []:
                for att in hw.get("attachmentIds", []) or []:
                    u = att.get("baseUrl", "") + att.get("key", "")
                    if u and not u.endswith(".pdf"):
                        content.append(f"{hw.get('topic', name)}:{u}\n")

        for hw in (item.get("dpp") or {}).get("homeworkIds", []) or []:
            for att in hw.get("attachmentIds", []) or []:
                u = att.get("baseUrl", "") + att.get("key", "")
                if u:
                    content.append(f"{hw.get('topic', name)}:{u}\n")
    return content


async def get_pwwp_all_todays_schedule_content(session: aiohttp.ClientSession, selected_batch_id: str, headers: Dict, editable: Message, start_time: float) -> List[str]:
    url = f"https://api.penpencil.co/v1/batches/{selected_batch_id}/todays-schedule"
    data = await fetch_pwwp_data(session, url, headers=headers)
    all_content = []
    if data and data.get("success") and data.get("data"):
        schedules = data["data"]
        total_items = len(schedules)
        
        for idx, item in enumerate(schedules):
            await update_status_card(
                editable=editable,
                task_name="Fetching Today's Schedule",
                current=idx + 1,
                total=total_items,
                start_time=start_time,
                activity=f"Fetching class details ({idx + 1}/{total_items})"
            )
            res = await get_pwwp_todays_schedule_content_details(
                session, selected_batch_id, item.get("batchSubjectId"), item.get("_id"), headers
            )
            all_content.extend(res)
            
    return all_content


async def process_pwwp(bot: Client, m: Message, user_id: int):
    api_headers = {
        "accept": "*/*", "accept-language": "en-US,en;q=0.9", "origin": "https://www.pw.live",
        "referer": "https://www.pw.live/", "user-agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/148.0.0.0 Safari/537.36",
        "client-id": "5eb393ee95fab7468a79d189", "client-type": "WEB", "content-type": "application/json",
        "randomid": str(uuid.uuid4()), "x-sdk-version": "0.0.25",
    }
    base_payload = {"organizationId": "5eb393ee95fab7468a79d189"}

    editable = await m.reply_text("**Wait initializing process... ⏳**")
    clean_name = None
    
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as session:
            raw_input = await prompt_user(
                bot, m, editable,
                "**Enter Your Account Access Token or Phone Number**\n\n**How To Get Access Token Video:** <blockquote>**https://t.me/+Af2HuNTEUa1iZDNl**</blockquote>",
                user_id
            )

            access_token = None
            if raw_input.isdigit() and len(raw_input) == 10:
                otp_payload = {**base_payload, "username": raw_input, "countryCode": "+91"}
                await editable.edit("**Sending OTP to registered phone... ⏳**")
                
                async with session.post("https://api.penpencil.co/v1/users/get-otp-secure?smsType=0", headers={**api_headers, "randomid": str(uuid.uuid4())}, json=otp_payload) as resp:
                    if resp.status >= 400:
                        await editable.edit(f"**OTP Request Failed ❌**\n`{await resp.text()}`")
                        return

                otp = await prompt_user(bot, m, editable, "**Enter OTP received on phone:**", user_id)
                if not otp.isdigit():
                    await editable.edit("**Invalid OTP format! ❌**")
                    return

                token_payload = {**base_payload, "client_id": "system-admin", "client_secret": "KjPXuAVfC5xbmgreETNMaL7z", "grant_type": "password", "latitude": 0, "longitude": 0, "username": raw_input, "otp": str(otp)}
                await editable.edit("**Verifying OTP... ⏳**")
                
                async with session.post("https://api.penpencil.co/v3/oauth/token", headers={**api_headers, "randomid": str(uuid.uuid4())}, json=token_payload) as resp:
                    res_data = await resp.json() if resp.status < 400 else {}
                    access_token = res_data.get("data", {}).get("access_token")
                    if not access_token:
                        await editable.edit("**Login Failed ❌ Invalid OTP or credentials.**")
                        return

                await editable.edit(f"**PW Login Successful ✅**\nToken generated.")
            else:
                access_token = raw_input

            auth_headers = {**api_headers, "authorization": f"Bearer {access_token}"}
            
            batch_search = await prompt_user(bot, m, editable, "**Enter Batch Name to Search:**", user_id)

            await editable.edit("**Searching courses online... 🔍**")
            courses_res = await fetch_pwwp_data(session, "https://api.penpencil.co/v3/batches/search", headers=auth_headers, params={"name": batch_search})
            courses = courses_res.get("data", []) if courses_res else []

            if not courses:
                await editable.edit("**No Batches Found! ❌\n\nAlso Check Your Access Token Is Not Expired Or Logged Out.**")
                return

            text_list = "\n".join([f"<blockquote>**{i+1}.** `{c.get('name', 'Batch')}`</blockquote>" for i, c in enumerate(courses)])
            idx_str = await prompt_user(bot, m, editable, f"**Select Course Index:**\n\n{text_list}", user_id)
            
            if not idx_str.isdigit() or not (1 <= int(idx_str) <= len(courses)):
                await editable.edit("**Invalid Selection ❌**")
                return

            selected_course = courses[int(idx_str) - 1]
            batch_id, batch_name = selected_course["_id"], selected_course.get("name", "Batch")
            clean_name = f"{batch_name.replace('/', '-').replace('|', '-')}"

            mode = await prompt_user(bot, m, editable, "**Choose Content Extraction Mode:**\n\n<blockquote>**1. Full Batch**</blockquote>\n\n<blockquote>**2. Today's Class**</blockquote>", user_id)
            if mode not in ("1", "2"):
                await editable.edit("**Invalid Choice! ❌**")
                return

            start_time = time.time()

            if mode == "1":
                await update_status_card(editable, f"Full Batch: {batch_name}", 0, 100, start_time, "Fetching batch details...")
                
                b_details = await fetch_pwwp_data(session, f"https://api.penpencil.co/v3/batches/{batch_id}/details", headers=auth_headers)
                subjects = b_details.get("data", {}).get("subjects", []) if b_details else []
                total_subjects = len(subjects)
                
                json_data, all_urls = {batch_name: {}}, {}
                zip_path = f"{clean_name}.zip"

                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                    for idx, sub in enumerate(subjects):
                        sub_name = sub.get("subject", "Unknown")
                        await update_status_card(
                            editable=editable,
                            task_name=f"Extracting: {batch_name}",
                            current=idx,
                            total=total_subjects,
                            start_time=start_time,
                            activity=f"Extracting subject: `{sub_name}`"
                        )
                        await process_pwwp_subject(session, sub, batch_id, batch_name, zipf, json_data, all_urls, auth_headers)

                await update_status_card(editable, f"Extracting: {batch_name}", total_subjects, total_subjects, start_time, "Compiling final text and JSON files...")
                
                with open(f"{clean_name}.json", "w", encoding="utf-8") as f:
                    json.dump(json_data, f, indent=4)
                    
                with open(f"{clean_name}.txt", "w", encoding="utf-8") as f:
                    for sub_urls in all_urls.values():
                        if sub_urls:
                            f.write("\n".join(sub_urls) + "\n")
            else:
                today_data = await get_pwwp_all_todays_schedule_content(session, batch_id, auth_headers, editable, start_time)
                with open(f"{clean_name}.txt", "w", encoding="utf-8") as f:
                    f.writelines(today_data)

            time_taken = format_time(time.time() - start_time)
            caption = f"**Batch Name:** `{batch_name}`\n**Time Taken:** `{time_taken}`"

            await editable.edit("📤 **Uploading generated documents to Telegram...**")
            
            uploaded_count = 0
            for ext in ["txt", "zip", "json"]:
                f_path = f"{clean_name}.{ext}"
                # Check that the file exists AND is greater than 0 bytes
                if os.path.exists(f_path) and os.path.getsize(f_path) > 0:
                    try:
                        with open(f_path, "rb") as doc:
                            await m.reply_document(doc, caption=caption, file_name=f"{clean_name}.{ext}")
                        uploaded_count += 1
                    except Exception as upload_err:
                        logging.error(f"Failed to upload {f_path}: {upload_err}")
                    finally:
                        if os.path.exists(f_path):
                            os.remove(f_path)
                elif os.path.exists(f_path):
                    # Remove zero-byte files safely without attempting upload
                    os.remove(f_path)

            if uploaded_count == 0:
                await editable.edit("**Extraction completed, but no content or links were found. (0 Bytes output) ❌**")
            else:
                await editable.delete()

    except ProcessCancelledException:
        if clean_name:
            for ext in ["txt", "zip", "json"]:
                f_path = f"{clean_name}.{ext}"
                if os.path.exists(f_path):
                    try:
                        os.remove(f_path)
                    except Exception:
                        pass
    except Exception as e:
        logging.exception("Error in process_pwwp:")
        if editable:
            await editable.edit(f"**Error : {e}**")
        if clean_name:
            for ext in ["txt", "zip", "json"]:
                f_path = f"{clean_name}.{ext}"
                if os.path.exists(f_path):
                    try:
                        os.remove(f_path)
                    except Exception:
                        pass


def register_pwwp_handlers(bot: Client):
    @bot.on_callback_query(filters.regex("^pwwp$"))
    async def pwwp_callback(client: Client, callback_query):
        user_id = callback_query.from_user.id
        await callback_query.answer()
       # if not is_authorized(user_id):
        #    await client.send_message(callback_query.message.chat.id, "**You Are Not Subscribed To This Bot.\nContact Owner.**")
       #     return
        asyncio.create_task(process_pwwp(client, callback_query.message, user_id))
