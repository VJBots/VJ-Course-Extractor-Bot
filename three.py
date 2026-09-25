import asyncio
import base64
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional
import aiohttp
from pyrogram import Client, filters
from pyrogram.types import Message

from helpers import appx_decrypt, ask_user, is_authorized


# Throttle API requests to prevent Appx rate-limiting / silent HTTP failures
SEMAPHORE = asyncio.Semaphore(15)


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


async def fetch_appx_html_to_json(session: aiohttp.ClientSession, url: str, headers: Dict = None, data: Any = None) -> Any:
    async with SEMAPHORE:
        for attempt in range(3):
            try:
                if data:
                    async with session.post(url, headers=headers, data=data) as response:
                        text = await response.text()
                else:
                    async with session.get(url, headers=headers) as response:
                        text = await response.text()

                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    match = re.search(r'\{"status":', text, re.DOTALL)
                    if match:
                        json_str = text[match.start():]
                        open_brace_count = 0
                        close_brace_count = 0
                        json_end = -1

                        for i, char in enumerate(json_str):
                            if char == '{':
                                open_brace_count += 1
                            elif char == '}':
                                close_brace_count += 1

                            if open_brace_count > 0 and open_brace_count == close_brace_count:
                                json_end = i + 1
                                break

                        if json_end != -1:
                            return json.loads(json_str[:json_end])
            except aiohttp.ClientError as e:
                logging.error(f"Appx Attempt {attempt + 1} failed for {url}: {e}")
            except Exception as e:
                logging.exception(f"Appx Unexpected error for {url}: {e}")
            if attempt < 2:
                await asyncio.sleep(1.5 ** attempt)
        return None


def extract_user_id_from_jwt(token: str) -> str:
    try:
        parts = token.split(".")
        if len(parts) == 3:
            payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
            payload_json = base64.urlsafe_b64decode(payload_b64).decode("utf-8")
            data = json.loads(payload_json)
            return str(data.get("id") or data.get("user_id") or data.get("sub") or "0")
    except Exception as e:
        logging.warning(f"Failed to parse user-id from token: {e}")
    return "0"


def find_appx_matching_apis(search_api: List[str], appxapis_file="threeapis.json") -> List[Dict]:
    matched_apis = []
    try:
        with open(appxapis_file, 'r') as f:
            api_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logging.error(f"Error reading appxapis file: {e}")
        return matched_apis

    for item in api_data:
        for term in search_api:
            term = term.strip().lower()
            if term in item["name"].lower() or term in item["api"].lower():
                matched_apis.append(item)

    unique_apis = []
    seen_apis = set()
    for item in matched_apis:
        if item["api"] not in seen_apis:
            unique_apis.append(item)
            seen_apis.add(item["api"])

    return unique_apis


async def resolve_api_and_app_name(bot: Client, m: Message, editable: Message, raw_input_text: str, user_id: int):
    raw_input_text = raw_input_text.strip()
    
    if raw_input_text.startswith(("http://", "https://")):
        clean_url = raw_input_text.replace("https://", "").replace("http://", "").rstrip("/")
        api_url = f"https://{clean_url}"
        return api_url, api_url

    search_terms = [term.strip() for term in raw_input_text.split()]
    matches = find_appx_matching_apis(search_terms)

    if not matches:
        await editable.edit("**No matches found! Enter Correct App Starting Word ❌**")
        return None, None

    text = ""
    for cnt, item in enumerate(matches):
        text += f"<blockquote>**{cnt + 1}.** `{item['name']}:{item['api']}`</blockquote>\n"

    selection_text = await prompt_user(bot, m, editable, f"**Select Index Number Of App API:**\n\n{text}", user_id)

    if selection_text.isdigit() and 1 <= int(selection_text) <= len(matches):
        selected_item = matches[int(selection_text) - 1]
        return selected_item['api'], selected_item['name']
    else:
        await editable.edit("**Error: Wrong Index Number ❌**")
        return None, None


async def login_appx_user(session: aiohttp.ClientSession, bot: Client, m: Message, editable: Message, user_id: int):
    """Handles credentials login flow, sends extracted token to user, and returns api, token, app_name."""
    app_input = await prompt_user(bot, m, editable, "**Enter App Name or API URL to login:**", user_id)
    api, app_name = await resolve_api_and_app_name(bot, m, editable, app_input, user_id)
    if not api or not app_name:
        return None, None, None

    mobile = await prompt_user(bot, m, editable, "**Enter Mobile Number:**", user_id)
    password = await prompt_user(bot, m, editable, "**Enter Password:**", user_id)

    await editable.edit("🔑 **Authenticating with Appx servers...**")

    headers = {
        "Client-Service": "Appx",
        "Auth-Key": "appxapi",
        "source": "website",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    login_url = f"{api}/post/userlogin"
    login_data = {
        "email": mobile,
        "password": password
    }

    res = await fetch_appx_html_to_json(session, login_url, headers=headers, data=login_data)

    if not res or res.get("status") != 200 or not res.get("data"):
        msg = res.get("message", "Invalid credentials or login API endpoint mismatch.") if res else "No response from server."
        await editable.edit(f"**Login Failed! ❌**\n`Reason: {msg}`")
        return None, None, None

    data = res["data"]
    token = data.get("token") or data.get("jwt_token") or data.get("user_token")

    if not token:
        await editable.edit("**Login successful, but token could not be found in response! ❌**")
        return None, None, None

    # Send token directly to user
    token_msg = (
        f"🔑 **Appx Token Generated Successfully!**\n\n"
        f"**App Name:** `{app_name}`\n"
        f"**Mobile:** `{mobile}`\n"
        f"**Token:**\n`{token}`\n\n"
        f"<blockquote>Tap token to copy it for future use.</blockquote>"
    )
    await bot.send_message(chat_id=m.chat.id, text=token_msg)

    return api, token, app_name


async def fetch_appx_video_id_details_v2(session: aiohttp.ClientSession, api: str, selected_batch_id: str, video_id: str, ytFlag: str, headers: Dict, folder_wise_course: Any, user_id: int) -> List[str]:
    try:
        headers_noauth = {k: v for k, v in headers.items() if k.lower() not in ('authorization', 'user-id')}
        
        res = await fetch_appx_html_to_json(session, f"{api}/get/fetchVideoDetailsById?course_id={selected_batch_id}&folder_wise_course={folder_wise_course}&ytflag={ytFlag}&video_id={video_id}", headers)
        if not res or res.get('status') != 200:
            res = await fetch_appx_html_to_json(session, f"{api}/get/fetchVideoDetailsById?course_id={selected_batch_id}&folder_wise_course={folder_wise_course}&ytflag={ytFlag}&video_id={video_id}", headers_noauth)

        output = []
        if res and res.get('data'):
            data = res.get('data')
            Title = data.get("Title", f"Video {video_id}")
            
            direct_video_url = (
                data.get('video_url') or data.get('videoUrl') or data.get('hls_url')
                or data.get('hlsUrl') or data.get('stream_url') or data.get('streamUrl')
                or data.get('media_url') or data.get('mediaUrl') or data.get('mpd_url')
                or data.get('mpdUrl') or data.get('download_url') or data.get('downloadUrl')
                or data.get('url') or data.get('file_url') or data.get('fileUrl')
                or data.get('source_url') or data.get('sourceUrl') or data.get('path')
                or data.get('link') or data.get('src') or data.get('video_link') or data.get('videoLink') or ""
            )
            
            if direct_video_url:
                output.append(f"{Title}:{direct_video_url}\n")
            else:
                res_drm = await fetch_appx_html_to_json(session, f"{api}/get/get_mpd_drm_links?videoid={video_id}&folder_wise_course={folder_wise_course}", headers)
                if not res_drm or res_drm.get('status') != 200:
                    res_drm = await fetch_appx_html_to_json(session, f"{api}/get/get_mpd_drm_links?videoid={video_id}&folder_wise_course={folder_wise_course}", headers_noauth)
                
                if res_drm:
                    drm_data = res_drm.get('data', [])
                    if drm_data and isinstance(drm_data, list) and len(drm_data) > 0:
                        path = appx_decrypt(drm_data[0].get("path", "")) if drm_data[0].get("path") else None
                        if path:
                            output.append(f"{Title}:{path}\n")
                    
                    if not output and drm_data and isinstance(drm_data, list):
                        for item in drm_data:
                            for field in ['path', 'url', 'videoUrl', 'hlsUrl', 'mpdUrl', 'streamUrl', 'mediaUrl', 'downloadUrl', 'fileUrl', 'link', 'src']:
                                val = item.get(field)
                                if val:
                                    try:
                                        decrypted = appx_decrypt(val) if val else None
                                        if decrypted and (decrypted.startswith('http') or decrypted.startswith('//')):
                                            if decrypted.startswith('//'):
                                                decrypted = f"https:{decrypted}"
                                            output.append(f"{Title}:{decrypted}\n")
                                            break
                                    except Exception:
                                        if val.startswith('http') or val.startswith('//'):
                                            if val.startswith('//'):
                                                val = f"https:{val}"
                                            output.append(f"{Title}:{val}\n")
                                            break
            
            pdf_link = appx_decrypt(data.get("pdf_link", "")) if data.get("pdf_link", "") and appx_decrypt(data.get("pdf_link", "")).endswith(".pdf") else None
            if pdf_link:
                if str(data.get("is_pdf_encrypted", 0)) == "1":
                    key = appx_decrypt(data.get("pdf_encryption_key", "")) if data.get("pdf_encryption_key") else None
                    output.append(f"{Title}:{pdf_link}*{key}\n" if key else f"{Title}:{pdf_link}\n")
                else:
                    output.append(f"{Title}:{pdf_link}\n")

            pdf_link2 = appx_decrypt(data.get("pdf_link2", "")) if data.get("pdf_link2", "") and appx_decrypt(data.get("pdf_link2", "")).endswith(".pdf") else None
            if pdf_link2:
                if str(data.get("is_pdf2_encrypted", 0)) == "1":
                    key = appx_decrypt(data.get("pdf2_encryption_key", "")) if data.get("pdf2_encryption_key") else None
                    output.append(f"{Title}:{pdf_link2}*{key}\n" if key else f"{Title}:{pdf_link2}\n")
                else:
                    output.append(f"{Title}:{pdf_link2}\n")
        return output
    except Exception as e:
        return [f"User ID: {user_id} - Error fetching details for Course_id : {selected_batch_id}, video ID {video_id}: {str(e)}\n"]


async def fetch_appx_folder_contents_v2(session: aiohttp.ClientSession, api: str, selected_batch_id: str, folder_id: str, headers: Dict, folder_wise_course: Any, user_id: int) -> List[str]:
    try:
        res = await fetch_appx_html_to_json(session, f"{api}/get/folder_contentsv2?course_id={selected_batch_id}&parent_id={folder_id}", headers)
        tasks, output = [], []
        if res and "data" in res:
            for item in res["data"]:
                video_id = item.get("id")
                ytFlag = item.get("ytFlag")
                if item.get("material_type") == "VIDEO":
                    tasks.append(fetch_appx_video_id_details_v2(session, api, selected_batch_id, video_id, ytFlag, headers, folder_wise_course, user_id))
                elif item.get("material_type") == "FOLDER":
                    tasks.append(fetch_appx_folder_contents_v2(session, api, selected_batch_id, video_id, headers, folder_wise_course, user_id))

        if tasks:
            results = await asyncio.gather(*tasks)
            for r in results:
                if isinstance(r, list):
                    output.extend(r)
                else:
                    output.append(r)
        return output
    except Exception as e:
        return [f"User ID: {user_id} - Error fetching folder contents: {e}\n"]


async def fetch_appx_video_id_details_v3(session: aiohttp.ClientSession, api: str, selected_batch_id: str, video_id: str, ytFlag: str, headers: Dict, user_id: int) -> List[str]:
    try:
        headers_noauth = {k: v for k, v in headers.items() if k.lower() not in ('authorization', 'user-id')}
        res = await fetch_appx_html_to_json(session, f"{api}/get/fetchVideoDetailsById?course_id={selected_batch_id}&folder_wise_course=0&ytflag={ytFlag}&video_id={video_id}", headers)
        
        if not res or res.get('status') != 200:
            res = await fetch_appx_html_to_json(session, f"{api}/get/fetchVideoDetailsById?course_id={selected_batch_id}&folder_wise_course=0&ytflag={ytFlag}&video_id={video_id}", headers_noauth)

        output = []
        if res and isinstance(res.get('data'), dict):
            data = res['data']
            Title = data.get("Title", f"Video {video_id}")
            raw_video_url = (
                data.get('video_url') or data.get('videoUrl') or data.get('hls_url')
                or data.get('hlsUrl') or data.get('stream_url') or data.get('streamUrl')
                or data.get('media_url') or data.get('mediaUrl') or data.get('mpd_url')
                or data.get('mpdUrl') or data.get('download_url') or data.get('downloadUrl')
                or data.get('url') or data.get('file_url') or data.get('fileUrl')
                or data.get('source_url') or data.get('sourceUrl') or data.get('path')
                or data.get('link') or data.get('src') or data.get('video_link')
                or data.get('videoLink') or ""
            )
            
            direct_video_url = None
            if raw_video_url:
                try:
                    decrypted_url = appx_decrypt(str(raw_video_url))
                    if decrypted_url and (decrypted_url.startswith("http://") or decrypted_url.startswith("https://") or decrypted_url.startswith("//")):
                        direct_video_url = f"https:{decrypted_url}" if decrypted_url.startswith("//") else decrypted_url
                except Exception:
                    if str(raw_video_url).startswith("http://") or str(raw_video_url).startswith("https://"):
                        direct_video_url = str(raw_video_url)

            if direct_video_url:
                output.append(f"{Title}:{direct_video_url}\n")
            else:
                res_drm = await fetch_appx_html_to_json(session, f"{api}/get/get_mpd_drm_links?folder_wise_course=0&videoid={video_id}", headers)
                if not res_drm or res_drm.get('status') != 200:
                    res_drm = await fetch_appx_html_to_json(session, f"{api}/get/get_mpd_drm_links?folder_wise_course=0&videoid={video_id}", headers_noauth)
                
                drm_data = res_drm.get('data', []) if res_drm else []
                if drm_data and isinstance(drm_data, list):
                    for item in drm_data:
                        if not isinstance(item, dict):
                            continue
                        for field in ['path', 'url', 'videoUrl', 'hlsUrl', 'mpdUrl', 'streamUrl', 'mediaUrl', 'downloadUrl', 'fileUrl', 'link', 'src']:
                            val = item.get(field)
                            if val:
                                try:
                                    decrypted = appx_decrypt(str(val))
                                    if decrypted and (decrypted.startswith('http') or decrypted.startswith('//') or decrypted.startswith('/')):
                                        if not decrypted.startswith('http'):
                                            decrypted = f"https:{decrypted}" if decrypted.startswith('//') else f"{api.rstrip('/')}/{decrypted.lstrip('/')}"
                                        output.append(f"{Title}:{decrypted}\n")
                                        break
                                except Exception:
                                    val_str = str(val)
                                    if val_str.startswith('http') or val_str.startswith('//'):
                                        if val_str.startswith('//'):
                                            val_str = f"https:{val_str}"
                                        output.append(f"{Title}:{val_str}\n")
                                        break
                        if output:
                            break
            
            pdf_link = appx_decrypt(data.get("pdf_link", "")) if data.get("pdf_link") else None
            if pdf_link and pdf_link.endswith(".pdf"):
                if str(data.get("is_pdf_encrypted", 0)) == "1":
                    key = appx_decrypt(data.get("pdf_encryption_key", "")) if data.get("pdf_encryption_key") else None
                    output.append(f"{Title}:{pdf_link}*{key}\n" if key else f"{Title}:{pdf_link}\n")
                else:
                    output.append(f"{Title}:{pdf_link}\n")

            pdf_link2 = appx_decrypt(data.get("pdf_link2", "")) if data.get("pdf_link2") else None
            if pdf_link2 and pdf_link2.endswith(".pdf"):
                if str(data.get("is_pdf2_encrypted", 0)) == "1":
                    key = appx_decrypt(data.get("pdf2_encryption_key", "")) if data.get("pdf2_encryption_key") else None
                    output.append(f"{Title}:{pdf_link2}*{key}\n" if key else f"{Title}:{pdf_link2}\n")
                else:
                    output.append(f"{Title}:{pdf_link2}\n")

        return output
    except Exception as e:
        return [f"User ID: {user_id} - Error fetching details V3 for course {selected_batch_id}, video {video_id}: {str(e)}\n"]


async def process_folder_wise_course_0(session: aiohttp.ClientSession, api: str, selected_batch_id: str, headers: Dict, user_id: int) -> List[str]:
    res = await fetch_appx_html_to_json(session, f"{api}/get/allsubjectfrmlivecourseclass?courseid={selected_batch_id}&start=-1", headers)
    all_outputs, tasks = [], []
    
    if res and "data" in res:
        for subject in res["data"]:
            subjectid = subject.get("subjectid")
            res2 = await fetch_appx_html_to_json(session, f"{api}/get/alltopicfrmlivecourseclass?courseid={selected_batch_id}&subjectid={subjectid}&start=-1", headers)
            if res2 and "data" in res2:
                for topic in res2["data"]:
                    topicid = topic.get("topicid")
                    res3 = await fetch_appx_html_to_json(session, f"{api}/get/livecourseclassbycoursesubtopconceptapiv3?topicid={topicid}&start=-1&courseid={selected_batch_id}&subjectid={subjectid}", headers)
                    if res3 and "data" in res3:
                        for item in res3["data"]:
                            Title = item.get("Title")
                            video_id = item.get("id")
                            ytFlag = item.get("ytFlag")

                            if item.get("material_type") in ("PDF", "TEST"):
                                pdf_link = appx_decrypt(item.get("pdf_link", "")) if item.get("pdf_link", "") and appx_decrypt(item.get("pdf_link", "")).endswith(".pdf") else None
                                if pdf_link:
                                    if str(item.get("is_pdf_encrypted")) == "1":
                                        key = appx_decrypt(item.get("pdf_encryption_key", ""))
                                        all_outputs.append(f"{Title}:{pdf_link}*{key}\n" if key else f"{Title}:{pdf_link}\n")
                                    else:
                                        all_outputs.append(f"{Title}:{pdf_link}\n")
                                        
                                pdf_link2 = appx_decrypt(item.get("pdf_link2", "")) if item.get("pdf_link2", "") and appx_decrypt(item.get("pdf_link2", "")).endswith(".pdf") else None
                                if pdf_link2:
                                    if str(item.get("is_pdf2_encrypted")) == "1":
                                        key = appx_decrypt(item.get("pdf2_encryption_key", ""))
                                        all_outputs.append(f"{Title}:{pdf_link2}*{key}\n" if key else f"{Title}:{pdf_link2}\n")
                                    else:
                                        all_outputs.append(f"{Title}:{pdf_link2}\n")

                            elif item.get("material_type") == "IMAGE":
                                thumbnail = item.get("thumbnail")
                                if thumbnail:
                                    all_outputs.append(f"{Title}:{thumbnail}\n")
                                    
                            elif item.get("material_type") == "VIDEO":
                                direct_video_url = (
                                    item.get('video_url') or item.get('videoUrl') or item.get('hls_url')
                                    or item.get('hlsUrl') or item.get('stream_url') or item.get('streamUrl')
                                    or item.get('media_url') or item.get('mediaUrl') or item.get('mpd_url')
                                    or item.get('mpdUrl') or item.get('download_url') or item.get('downloadUrl')
                                    or item.get('url') or item.get('file_url') or item.get('fileUrl')
                                    or item.get('video_link') or item.get('videoLink') or item.get('source_url')
                                    or item.get('sourceUrl') or item.get('path') or item.get('link') or item.get('src')
                                )
                                if not direct_video_url:
                                    direct_video_url = (
                                        appx_decrypt(item.get("pdf_link", "")) if item.get("pdf_link") and not appx_decrypt(item.get("pdf_link", "")).endswith(".pdf") else None
                                        or appx_decrypt(item.get("pdf_link2", "")) if item.get("pdf_link2") and not appx_decrypt(item.get("pdf_link2", "")).endswith(".pdf") else None
                                        or appx_decrypt(item.get("file_link", "")) if item.get("file_link") else None
                                    )
                                
                                if direct_video_url:
                                    if direct_video_url.startswith("http"):
                                        all_outputs.append(f"{Title}:{direct_video_url}\n")
                                    elif '/' in direct_video_url:
                                        constructed = f"{api.rstrip('/')}/{direct_video_url.lstrip('/')}"
                                        all_outputs.append(f"{Title}:{constructed}\n")
                                else:
                                    if selected_batch_id is not None and video_id is not None and ytFlag is not None:
                                        tasks.append(fetch_appx_video_id_details_v3(session, api, selected_batch_id, video_id, ytFlag, headers, user_id))

    if tasks:
        results = await asyncio.gather(*tasks)
        for res in results:
            all_outputs.extend(res)

    return all_outputs


async def process_folder_wise_course_1(session: aiohttp.ClientSession, api: str, selected_batch_id: str, headers: Dict, user_id: int) -> List[str]:
    res = await fetch_appx_html_to_json(session, f"{api}/get/folder_contentsv2?course_id={selected_batch_id}&parent_id=-1", headers)
    all_outputs, tasks = [], []
    
    if res and "data" in res:
        for item in res["data"]:
            Title = item.get("Title")
            video_id = item.get("id")
            ytFlag = item.get("ytFlag")
            
            if item.get("material_type") in ("PDF", "TEST"):
                pdf_link = appx_decrypt(item.get("pdf_link", "")) if item.get("pdf_link", "") and appx_decrypt(item.get("pdf_link", "")).endswith(".pdf") else None
                if pdf_link:
                    if str(item.get("is_pdf_encrypted")) == "1":
                        key = appx_decrypt(item.get("pdf_encryption_key", ""))
                        all_outputs.append(f"{Title}:{pdf_link}*{key}\n" if key else f"{Title}:{pdf_link}\n")
                    else:
                        all_outputs.append(f"{Title}:{pdf_link}\n")
                        
                pdf_link2 = appx_decrypt(item.get("pdf_link2", "")) if item.get("pdf_link2", "") and appx_decrypt(item.get("pdf_link2", "")).endswith(".pdf") else None
                if pdf_link2:
                    if str(item.get("is_pdf2_encrypted")) == "1":
                        key = appx_decrypt(item.get("pdf2_encryption_key", ""))
                        all_outputs.append(f"{Title}:{pdf_link2}*{key}\n" if key else f"{Title}:{pdf_link2}\n")
                    else:
                        all_outputs.append(f"{Title}:{pdf_link2}\n")

            elif item.get("material_type") == "IMAGE":
                thumbnail = item.get("thumbnail")
                if thumbnail:
                    all_outputs.append(f"{Title}:{thumbnail}\n")
                   
            elif item.get("material_type") == "VIDEO":
                direct_video_url = (
                    item.get('video_url') or item.get('videoUrl') or item.get('hls_url')
                    or item.get('hlsUrl') or item.get('stream_url') or item.get('streamUrl')
                    or item.get('media_url') or item.get('mediaUrl') or item.get('mpd_url')
                    or item.get('mpdUrl') or item.get('download_url') or item.get('downloadUrl')
                    or item.get('url') or item.get('file_url') or item.get('fileUrl')
                    or item.get('video_link') or item.get('videoLink') or item.get('source_url')
                    or item.get('sourceUrl') or item.get('path') or item.get('link') or item.get('src')
                )
                if not direct_video_url:
                    direct_video_url = (
                        appx_decrypt(item.get("pdf_link", "")) if item.get("pdf_link") and not appx_decrypt(item.get("pdf_link", "")).endswith(".pdf") else None
                        or appx_decrypt(item.get("pdf_link2", "")) if item.get("pdf_link2") and not appx_decrypt(item.get("pdf_link2", "")).endswith(".pdf") else None
                        or appx_decrypt(item.get("file_link", "")) if item.get("file_link") else None
                    )
                if direct_video_url:
                    if direct_video_url.startswith("http"):
                        all_outputs.append(f"{Title}:{direct_video_url}\n")
                    elif '/' in direct_video_url:
                        constructed = f"{api.rstrip('/')}/{direct_video_url.lstrip('/')}"
                        all_outputs.append(f"{Title}:{constructed}\n")
                else:
                    tasks.append(fetch_appx_video_id_details_v2(session, api, selected_batch_id, video_id, ytFlag, headers, 1, user_id))

            elif item.get("material_type") == "FOLDER":
                tasks.append(fetch_appx_folder_contents_v2(session, api, selected_batch_id, item.get("id"), headers, 1, user_id))

    if tasks:
        results = await asyncio.gather(*tasks)
        for res in results:
            all_outputs.extend(res)

    return all_outputs


async def process_appxwp(bot: Client, m: Message, user_id: int):
    editable = await m.reply_text("**Wait initializing process... ⏳**")
    clean_file_name = None

    try:
        connector = aiohttp.TCPConnector(limit=100)
        async with aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=60)) as session:
            
            # Offer initial authentication choice
            auth_prompt = (
                "**Select Appx Authentication Option:**\n\n"
                "**1. 🔑 Login with Credentials (Mobile & Password)**\n"
                "**2. 🎫 Enter JWT/Access Token or App Name Directly**"
            )
            auth_mode = await prompt_user(bot, m, editable, auth_prompt, user_id)

            api = None
            token = None
            selected_app_name = None

            if auth_mode == "1":
                api, token, selected_app_name = await login_appx_user(session, bot, m, editable, user_id)
                if not api or not token:
                    return
            else:
                first_input = await prompt_user(bot, m, editable, "**Enter App Name, API Url, or JWT/Access Token:**", user_id)

                if first_input.count('.') == 2 and len(first_input) > 100:
                    token = first_input
                    extracted_jwt_userid = extract_user_id_from_jwt(token)
                    
                    second_input = await prompt_user(
                        bot, m, editable,
                        f"**Token received! (Detected User ID: `{extracted_jwt_userid}`)\nNow enter App Name or API URL:**",
                        user_id
                    )
                    api, selected_app_name = await resolve_api_and_app_name(bot, m, editable, second_input, user_id)
                else:
                    api, selected_app_name = await resolve_api_and_app_name(bot, m, editable, first_input, user_id)

            if not api or not selected_app_name:
                return

            extracted_jwt_userid = extract_user_id_from_jwt(token) if token else "0"
            formatted_token = f"{token}" if token and not token.startswith("Bearer ") else token

            headers = {
                "Client-Service": "Appx",
                "Auth-Key": "appxapi",
                "source": "website",
            }
            if token:
                headers['Authorization'] = formatted_token
                headers['User-ID'] = extracted_jwt_userid

            try: await editable.delete()
            except: pass
            editable = await m.reply_text("**Fetching Available Courses... 🔍**")
            res1 = await fetch_appx_html_to_json(session, f"{api}/get/courselist", headers)
            res2 = await fetch_appx_html_to_json(session, f"{api}/get/courselistnewv2", headers)

            courses1 = res1.get("data", []) if res1 and res1.get('status') == 200 else []
            courses2 = res2.get("data", []) if res2 and res2.get('status') == 200 else []
            courses3 = []

            if token:
                res3 = await fetch_appx_html_to_json(session, f"{api}/get/mycourse", headers)
                if res3 and res3.get('status') == 200:
                    courses3 = res3.get("data", [])

            courses = courses3 + courses1 + courses2
            if not courses:
                await editable.edit("**Did not find any course! ❌\nCheck if token is expired or if the App API endpoint is valid.**")
                return

            total = len(courses)
            if total > 50:
                text = ""
                for cnt, course in enumerate(courses):
                    text += f"{cnt + 1}. {course.get('course_name', 'Unnamed Course')} 💵₹{course.get('price', '0')}\n"

                course_details_file = f"{user_id}_paid_course_details.txt"
                with open(course_details_file, 'w', encoding='utf-8') as f:
                    f.write(text)

                caption = f"**App Name:** `{selected_app_name}`\n**Batch Name:** `Course Details`"

                try:
                    with open(course_details_file, 'rb') as f:
                        await m.reply_document(document=f, caption=caption, file_name="course_details.txt")
                finally:
                    if os.path.exists(course_details_file):
                        os.remove(course_details_file)

                selection_course = await prompt_user(bot, m, editable, "**Send index number from the course details file which i just send you:**", user_id)
            else:
                text = ""
                for cnt, course in enumerate(courses):
                    text += f"<blockquote>**{cnt + 1}.** `{course.get('course_name', 'Unnamed Course')} 💵₹{course.get('price', '0')}`</blockquote>\n"
                selection_course = await prompt_user(bot, m, editable, f"**Send index number of the course to download:**\n\n{text}", user_id)

            if selection_course.isdigit() and 1 <= int(selection_course) <= len(courses):
                selected_course_index = int(selection_course) - 1
                course = courses[selected_course_index]
                selected_batch_id = course['id']
                selected_batch_name = course.get('course_name', 'Batch')
                folder_wise_course = course.get("folder_wise_course", "")
                
                clean_batch_name = selected_batch_name.replace('/', '-').replace('|', '-')[:244]
                clean_file_name = f"{user_id}_{clean_batch_name}"
            else:
                await editable.edit("**Invalid Selection Index! ❌**")
                return

            start_time = time.time()
            await update_status_card(editable, f"Extracting: {selected_batch_name}", 0, 100, start_time, "Initializing extraction...")

            extraction_headers = {
                "Client-Service": "Appx",
                "Auth-Key": "appxapi",
                "source": "website",
            }
            if token:
                extraction_headers["Authorization"] = formatted_token
                extraction_headers["User-ID"] = extracted_jwt_userid

            all_outputs = []

            if folder_wise_course == 0:
                await update_status_card(editable, f"Extracting: {selected_batch_name}", 20, 100, start_time, "Extracting live/subject course items...")
                all_outputs = await process_folder_wise_course_0(session, api, selected_batch_id, extraction_headers, user_id)
            elif folder_wise_course == 1:
                await update_status_card(editable, f"Extracting: {selected_batch_name}", 20, 100, start_time, "Extracting folder-wise structure...")
                all_outputs = await process_folder_wise_course_1(session, api, selected_batch_id, extraction_headers, user_id)
            else:
                await update_status_card(editable, f"Extracting: {selected_batch_name}", 10, 100, start_time, "Extracting method 1...")
                outputs_0 = await process_folder_wise_course_0(session, api, selected_batch_id, extraction_headers, user_id)
                all_outputs.extend(outputs_0)
                await update_status_card(editable, f"Extracting: {selected_batch_name}", 50, 100, start_time, "Extracting method 2...")
                outputs_1 = await process_folder_wise_course_1(session, api, selected_batch_id, extraction_headers, user_id)
                all_outputs.extend(outputs_1)

            if all_outputs:
                output_txt_path = f"{clean_file_name}.txt"
                with open(output_txt_path, 'w', encoding='utf-8') as f:
                    for output_line in all_outputs:
                        f.write(output_line)

                time_taken = format_time(time.time() - start_time)
                caption = f"**App Name:** `{selected_app_name}`\n**Batch Name:** `{selected_batch_name}`\n**Time Taken:** `{time_taken}`"

                await editable.edit("📤 **Uploading generated document to Telegram...**")

                if os.path.exists(output_txt_path) and os.path.getsize(output_txt_path) > 0:
                    try:
                        with open(output_txt_path, "rb") as doc:
                            await m.reply_document(doc, caption=caption, file_name=f"{clean_batch_name}.txt")
                        await editable.delete()
                    except Exception as upload_err:
                        logging.error(f"Failed to upload output file: {upload_err}")
                    finally:
                        if os.path.exists(output_txt_path):
                            os.remove(output_txt_path)
                else:
                    if os.path.exists(output_txt_path):
                        os.remove(output_txt_path)
                    await editable.edit("**Extraction completed, but no content was found (0 Bytes output). ❌**")
            else:
                await editable.edit("**Didn't Find Any Content In The Course! ❌**")

    except ProcessCancelledException:
        if clean_file_name:
            f_path = f"{clean_file_name}.txt"
            if os.path.exists(f_path):
                try:
                    os.remove(f_path)
                except Exception:
                    pass
    except Exception as e:
        logging.exception("Error in process_appxwp:")
        if editable:
            await editable.edit(f"**Error : {e}**")
        if clean_file_name:
            f_path = f"{clean_file_name}.txt"
            if os.path.exists(f_path):
                try:
                    os.remove(f_path)
                except Exception:
                    pass


def register_appxwp_handlers(bot: Client):
    @bot.on_callback_query(filters.regex("^appxwp$"))
    async def appxwp_callback(client: Client, callback_query):
        user_id = callback_query.from_user.id
        await callback_query.answer()
      #  if not is_authorized(user_id):
     #       await client.send_message(callback_query.message.chat.id, "**You Are Not Subscribed To This Bot.\nContact Owner.**")
     #       return
            
        asyncio.create_task(process_appxwp(client, callback_query.message, user_id))
