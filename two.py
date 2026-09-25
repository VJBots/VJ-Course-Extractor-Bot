import asyncio
import logging
import os
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple
import aiohttp
from pyrogram import Client, filters
from pyrogram.types import Message

from helpers import ask_user, is_authorized


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


SEMAPHORE = asyncio.Semaphore(10)


async def fetch_cpwp_signed_url(url_val: str, name: str, session: aiohttp.ClientSession, headers: Dict[str, str]) -> Optional[str]:
    async with SEMAPHORE:
        try:
            async with session.get("https://api.classplusapp.com/cams/uploader/video/jw-signed-url", params={"url": url_val}, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("url") or data.get("drmUrls", {}).get("manifestUrl")
        except Exception as e:
            logging.error(f"Error fetching signed URL for {name}: {e}")
        return None


async def process_cpwp_url(url_val: str, name: str, session: aiohttp.ClientSession, headers: Dict[str, str]) -> Optional[str]:
    try:
        signed_url = await fetch_cpwp_signed_url(url_val, name, session, headers)
        if not signed_url:
            logging.warning(f"Failed to obtain signed URL for {name}: {url_val}")
            return None

        if "testbook.com" in url_val or "classplusapp.com/drm" in url_val or "media-cdn.classplusapp.com/drm" in url_val:
            return f"{name}:{url_val}\n"

        async with SEMAPHORE:
            async with session.get(signed_url) as response:
                response.raise_for_status()
                return f"{name}:{signed_url}\n"

    except Exception:
        pass
    return None


async def get_cpwp_course_content(
    session: aiohttp.ClientSession,
    headers: Dict[str, str],
    Batch_Token: str,
    editable: Message,
    start_time: float,
    folder_id: int = 0,
    limit: int = 9999999999,
    retry_count: int = 0,
    progress_stats: Optional[Dict[str, int]] = None
) -> Tuple[List[str], int, int, int]:
    if progress_stats is None:
        progress_stats = {"processed": 0, "total": 1}

    MAX_RETRIES = 3
    fetched_urls: set[str] = set()
    results: List[str] = []
    video_count = 0
    pdf_count = 0
    image_count = 0
    content_tasks: List[Tuple[int, asyncio.Task[Optional[str]]]] = []
    folder_tasks: List[Tuple[int, asyncio.Task[Tuple[List[str], int, int, int]]]] = []

    try:
        content_api = f'https://api.classplusapp.com/v2/course/preview/content/list/{Batch_Token}'
        params = {'folderId': folder_id, 'limit': limit}

        async with SEMAPHORE:
            async with session.get(content_api, params=params, headers=headers) as res:
                res.raise_for_status()
                res_json = await res.json()
                contents: List[Dict[str, Any]] = res_json.get('data', [])

            progress_stats["total"] += len(contents)

            for content in contents:
                progress_stats["processed"] += 1
                current_item = content.get('name', 'Item')
                
                if progress_stats["processed"] % 5 == 0 or progress_stats["processed"] == progress_stats["total"]:
                    await update_status_card(
                        editable=editable,
                        task_name="Scanning Course Contents",
                        current=progress_stats["processed"],
                        total=progress_stats["total"],
                        start_time=start_time,
                        activity=f"Scanning: `{current_item[:30]}`"
                    )

                if content.get('contentType') == 1:
                    folder_task = asyncio.create_task(
                        get_cpwp_course_content(
                            session, headers, Batch_Token, editable, start_time,
                            folder_id=content['id'], retry_count=0, progress_stats=progress_stats
                        )
                    )
                    folder_tasks.append((content['id'], folder_task))

                else:
                    name: str = content.get('name', '')
                    url_val: Optional[str] = content.get('url') or content.get('thumbnailUrl')

                    if not url_val:
                        logging.warning(f"No URL found for content: {name}")
                        continue

                    if "media-cdn.classplusapp.com/tencent/" in url_val:
                        url_val = url_val.rsplit('/', 1)[0] + "/master.m3u8"
                    elif "media-cdn.classplusapp.com" in url_val and url_val.endswith('.jpg'):
                        identifier = url_val.split('/')[-3]
                        url_val = f'https://media-cdn.classplusapp.com/alisg-cdn-a.classplusapp.com/{identifier}/master.m3u8'
                    elif "tencdn.classplusapp.com" in url_val and url_val.endswith('.jpg'):
                        identifier = url_val.split('/')[-2]
                        url_val = f'https://media-cdn.classplusapp.com/tencent/{identifier}/master.m3u8'
                    elif "4b06bf8d61c41f8310af9b2624459378203740932b456b07fcf817b737fbae27" in url_val and url_val.endswith('.jpeg'):
                        url_val = f'https://media-cdn.classplusapp.com/alisg-cdn-a.classplusapp.com/b08bad9ff8d969639b2e43d5769342cc62b510c4345d2f7f153bec53be84fe35/{url_val.split("/")[-1].split(".")[0]}/master.m3u8'
                    elif "cpvideocdn.testbook.com" in url_val and url_val.endswith('.png'):
                        match = re.search(r'/streams/([a-f0-9]{24})/', url_val)
                        video_id = match.group(1) if match else url_val.split('/')[-2]
                        url_val = f'https://cpvod.testbook.com/{video_id}/playlist.m3u8'
                    elif "media-cdn.classplusapp.com/drm/" in url_val and url_val.endswith('.png'):
                        video_id = url_val.split('/')[-3]
                        url_val = f'https://media-cdn.classplusapp.com/drm/{video_id}/playlist.m3u8'
                    elif "https://media-cdn.classplusapp.com" in url_val and ("cc/" in url_val or "lc/" in url_val or "uc/" in url_val or "dy/" in url_val) and url_val.endswith('.png'):
                        url_val = url_val.replace('thumbnail.png', 'master.m3u8')
                    elif "https://tb-video.classplusapp.com" in url_val and url_val.endswith('.jpg'):
                        video_id = url_val.split('/')[-1].split('.')[0]
                        url_val = f'https://tb-video.classplusapp.com/{video_id}/master.m3u8'

                    if url_val.endswith(("master.m3u8", "playlist.m3u8")) and url_val not in fetched_urls:
                        fetched_urls.add(url_val)
                        task = asyncio.create_task(process_cpwp_url(url_val, name, session, headers))
                        content_tasks.append((content['id'], task))

                    else:
                        url_val = content.get('url')
                        if url_val:
                            fetched_urls.add(url_val)
                            results.append(f"{name}:{url_val}\n")
                            if url_val.endswith('.pdf'):
                                pdf_count += 1
                            else:
                                image_count += 1

    except Exception as e:
        logging.exception(f"An unexpected error occurred: {e}")
        if retry_count < MAX_RETRIES:
            logging.info(f"Retrying folder {folder_id} (Attempt {retry_count + 1}/{MAX_RETRIES})")
            await asyncio.sleep(2 ** retry_count)
            return await get_cpwp_course_content(
                session, headers, Batch_Token, editable, start_time,
                folder_id, limit, retry_count + 1, progress_stats
            )
        else:
            logging.error(f"Failed to retrieve folder {folder_id} after {MAX_RETRIES} retries.")
            return [], 0, 0, 0

    content_results = await asyncio.gather(*(task for _, task in content_tasks), return_exceptions=True)

    for (f_id, _), result in zip(content_tasks, content_results):
        if isinstance(result, Exception):
            logging.error(f"Task failed with exception: {result}")
        elif result:
            results.append(result)
            video_count += 1

    for f_id, folder_task in folder_tasks:
        try:
            res = await folder_task
            if res and isinstance(res, tuple) and len(res) == 4:
                nested_results, nested_video_count, nested_pdf_count, nested_image_count = res
                if nested_results:
                    results.extend(nested_results)
                video_count += nested_video_count
                pdf_count += nested_pdf_count
                image_count += nested_image_count
        except Exception as e:
            logging.error(f"Error processing folder {f_id}: {e}")

    return results, video_count, pdf_count, image_count


async def process_cpwp(bot: Client, m: Message, user_id: int):
    headers = {
        'accept-encoding': 'gzip',
        'accept-language': 'EN',
        'api-version': '35',
        'app-version': '1.4.71.1',
        'build-number': '35',
        'connection': 'Keep-Alive',
        'content-type': 'application/json',
        'device-details': 'Xiaomi_Redmi 7_SDK-32',
        'device-id': 'cc4473819ba3ee7f51f560f801574304',
        'host': 'api.classplusapp.com',
        'region': 'IN',
        'user-agent': 'Mobile-Android',
        'webengage-luid': '00000187-6fe4-5d41-a530-26186858be4c'
    }

    connector = aiohttp.TCPConnector(limit=1000)
    async with aiohttp.ClientSession(connector=connector) as session:
        editable = None
        file_path = None
        try:
            editable = await m.reply_text("**Processing Classplus request... ⏳**")

            org_code = await prompt_user(bot, m, editable, "**Enter ORG Code Of Your Classplus App:**", user_id)
            org_code = org_code.lower().strip()

            raw_input = await prompt_user(bot, m, editable, "**Enter Access Token OR 10-digit Mobile Number:**", user_id)
            raw_input = raw_input.strip()

            access_token = None
            if raw_input.isdigit() and len(raw_input) == 10:
                await editable.edit("**Fetching Organization Info... ⏳**")

                org_info_url = f"https://api.classplusapp.com/v2/orgs/{org_code}"
                async with session.get(org_info_url, headers=headers) as org_resp:
                    if org_resp.status != 200:
                        await editable.edit(f"**Invalid Org Code ❌**\n`{await org_resp.text()}`")
                        return

                    org_data = await org_resp.json()
                    org_id = org_data.get("data", {}).get("orgId") or org_data.get("data", {}).get("id")

                if not org_id:
                    await editable.edit("**Could not resolve Organization ID ❌**")
                    return

                await editable.edit("**Sending OTP to Mobile Number... ⏳**")

                otp_headers = {**headers, "api-version": "52"}

                otp_req_payload = {
                    "countryExt": "91",
                    "mobile": raw_input,
                    "orgId": int(org_id),
                    "orgCode": org_code
                }
                async with session.post("https://api.classplusapp.com/v2/otp/generate", json=otp_req_payload, headers=otp_headers) as otp_resp:
                    if otp_resp.status != 200:
                        await editable.edit(f"**Failed to Send OTP ❌**\n`{await otp_resp.text()}`")
                        return

                    otp_data = await otp_resp.json()
                    session_id = otp_data.get("data", {}).get("sessionId")

                otp = await prompt_user(bot, m, editable, "**Enter OTP received on phone:**", user_id)
                if not otp.isdigit():
                    await editable.edit("**Invalid OTP ❌**")
                    return

                await editable.edit("**Verifying OTP... ⏳**")
                verify_payload = {
                    "otp": str(otp.strip()),
                    "countryExt": "91",
                    "sessionId": str(session_id),
                    "orgId": int(org_id),
                    "fingerprintId": headers.get("device-id", "cc4473819ba3ee7f51f560f801574304"),
                    "mobile": raw_input
                }
                async with session.post("https://api.classplusapp.com/v2/users/verify", json=verify_payload, headers=otp_headers) as verify_resp:
                    ver_json = await verify_resp.json()
                    if verify_resp.status != 200 or ver_json.get("status") == "failure":
                        err_msg = ver_json.get("message") or await verify_resp.text()
                        await editable.edit(f"**OTP Verification Failed ❌**\n`{err_msg}`")
                        return

                    access_token = (
                        ver_json.get("data", {}).get("token")
                        or ver_json.get("data", {}).get("user", {}).get("token")
                        or ver_json.get("token")
                    )

                if not access_token:
                    await editable.edit("**Failed to retrieve Access Token from Classplus ❌**")
                    return

                await editable.edit(f"**Classplus Login Successful ✅**\n\n**Token:** `{access_token}`\n\n**Do not share this token with anyone save it anywhere in private.**")
                editable = await m.reply_text("**Wait Processing Your Request....**")
            else:
                access_token = raw_input

            headers['x-access-token'] = access_token

            hash_headers = {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'Accept-Encoding': 'gzip, deflate, br, zstd',
                'Accept-Language': 'en-US,en;q=0.9',
                'Referer': f'https://{org_code}.courses.store/?mainCategory=0',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36'
            }

            async with session.get(f"https://{org_code}.courses.store", headers=hash_headers) as response:
                html_text = await response.text()
                hash_match = re.search(r'["\']hash["\']\s*:\s*["\']([^"\']+)["\']', html_text)

                if not hash_match:
                    await editable.edit("**No App Found In Org Code ❌**")
                    return

                token = hash_match.group(1)

                async with session.get(f"https://api.classplusapp.com/v2/course/preview/similar/{token}?limit=20", headers=headers) as resp:
                    if resp.status != 200:
                        await editable.edit(f"**Error Fetching Courses:** `{await resp.text()}`")
                        return

                    res_json = await resp.json()
                    courses = res_json.get('data', {}).get('coursesData', [])

                    if not courses:
                        await editable.edit("**Didn't Find Any Course ❌**")
                        return

                    text = ''.join([f"<blockquote>**{cnt + 1}.** `\n{c['name']} 💵₹{c['finalPrice']}`</blockquote>\n" for cnt, c in enumerate(courses)])
                    raw_text2 = await prompt_user(bot, m, editable, f"**Send index number of the Category Name**\n\n{text}\n**If Your Batch Not Listed Then Enter Your Batch Name**", user_id)

                    raw_text2 = raw_text2.strip()
                    if raw_text2.isdigit() and 1 <= int(raw_text2) <= len(courses):
                        selected_course_index = int(raw_text2)
                        course = courses[selected_course_index - 1]
                    else:
                        search_url = f"https://api.classplusapp.com/v2/course/preview/similar/{token}?search={raw_text2}"
                        async with session.get(search_url, headers=headers) as search_resp:
                            if search_resp.status == 200:
                                search_json = await search_resp.json()
                                search_courses = search_json.get("data", {}).get("coursesData", [])

                                if not search_courses:
                                    await editable.edit("**Didn't Find Any Course Matching The Search Term ❌**")
                                    return

                                text_search = ''.join([f"<blockquote>**{cnt + 1}.** `\n{c['name']} 💵₹{c['finalPrice']}`</blockquote>\n" for cnt, c in enumerate(search_courses)])
                                raw_text3 = await prompt_user(bot, m, editable, f"**Send index number of the Batch to download.**\n\n{text_search}", user_id)

                                raw_text3 = raw_text3.strip()
                                if raw_text3.isdigit() and 1 <= int(raw_text3) <= len(search_courses):
                                    selected_course_index = int(raw_text3)
                                    course = search_courses[selected_course_index - 1]
                                else:
                                    await editable.edit("**Wrong Index Number ❌**")
                                    return
                            else:
                                await editable.edit(f"**Error:** `{await search_resp.text()}`")
                                return

                    selected_batch_id = course['id']
                    selected_batch_name = course['name']
                    clean_batch_name = re.sub(r'[\\/*?:"<>|]', "-", selected_batch_name)
                    file_path = f"{clean_batch_name}.txt"

                    batch_headers = {
                        'Accept': 'application/json, text/plain, */*',
                        'region': 'IN',
                        'accept-language': 'EN',
                        'Api-Version': '22',
                        'x-access-token': access_token,
                        'tutorWebsiteDomain': f'https://{org_code}.courses.store'
                    }

                    params = {'courseId': f'{selected_batch_id}'}

                    async with session.get("https://api.classplusapp.com/v2/course/preview/org/info", params=params, headers=batch_headers) as info_resp:
                        if info_resp.status == 200:
                            res_info = await info_resp.json()
                            Batch_Token = res_info['data']['hash']
                            App_Name = res_info['data']['name']

                            start_time = time.time()
                            await update_status_card(
                                editable=editable,
                                task_name=f"Extracting: {selected_batch_name}",
                                current=0,
                                total=100,
                                start_time=start_time,
                                activity="Initializing content crawler..."
                            )

                            course_content, video_count, pdf_count, image_count = await get_cpwp_course_content(
                                session, headers, Batch_Token, editable, start_time
                            )

                            if course_content:
                                await update_status_card(
                                    editable=editable,
                                    task_name=f"Extracting: {selected_batch_name}",
                                    current=100,
                                    total=100,
                                    start_time=start_time,
                                    activity="Saving content links to file..."
                                )

                                with open(file_path, 'w', encoding='utf-8') as f:
                                    f.write(''.join(course_content))

                                formatted_time = format_time(time.time() - start_time)

                                await editable.delete()

                                caption = f"**App Name : ```\n{App_Name}({org_code})```\nBatch Name : ```\n{selected_batch_name}``````\n🎬 : {video_count} | 📁 : {pdf_count} | 🖼  : {image_count}``````\nTime Taken : {formatted_time}```**"

                                with open(file_path, 'rb') as f:
                                    await m.reply_document(document=f, caption=caption, file_name=f"{clean_batch_name}.txt")

                                if os.path.exists(file_path):
                                    os.remove(file_path)
                            else:
                                await editable.edit("**Didn't Find Any Content In The Course ❌**")
                        else:
                            await editable.edit(f"**Error:** `{await info_resp.text()}`")

        except ProcessCancelledException:
            pass
        except Exception as e:
            logging.exception("Error in process_cpwp:")
            if editable:
                await editable.edit(f"**Error : {e}**")
        finally:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception:
                    pass


def register_cpwp_handlers(bot: Client):
    @bot.on_callback_query(filters.regex("^cpwp$"))
    async def cpwp_callback(client: Client, callback_query):
        user_id = callback_query.from_user.id
        await callback_query.answer()
      #  if not is_authorized(user_id):
      #      await client.send_message(callback_query.message.chat.id, "**You Are Not Subscribed To This Bot.\nContact Owner.**")
      #      return
        asyncio.create_task(process_cpwp(client, callback_query.message, user_id))
