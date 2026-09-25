"""
PW/Classplus/Appx Course Extractor Bot - Railway/Render/Koyeb/Web Edition
"""
import os
import threading

# Minimal web server for web health checks
def run_web():
    port = int(os.environ.get("PORT", 8080))
    try:
        from flask import Flask
        app = Flask(__name__)
        @app.route("/")
        def health():
            return "Bot running", 200
        app.run(host="0.0.0.0", port=port)
    except:
        import http.server
        import socketserver
        handler = http.server.SimpleHTTPRequestHandler
        with socketserver.TCPServer(("", port), handler) as httpd:
            httpd.serve_forever()

# Start web server in background thread
threading.Thread(target=run_web, daemon=True).start()



import requests
import asyncio
import aiohttp
import json
import zipfile
from typing import Dict, List, Any, Tuple
from collections import defaultdict
from base64 import b64encode, b64decode
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
import os
import base64
from pyrogram import Client, filters
import sys
import re
import requests
import uuid
import random
import string
import hashlib
from pyrogram.types.messages_and_media import message
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import FloodWait
from pyromod import listen
from pyromod.exceptions.listener_timeout import ListenerTimeout
from pyrogram.types import Message
import pyrogram
from pyrogram import Client, filters
from pyrogram.types import User, Message
from pyrogram.enums import ChatMemberStatus
from pyrogram.raw.functions.channels import GetParticipants
from config import api_id, api_hash, bot_token, auth_users
from datetime import datetime
import time
from concurrent.futures import ThreadPoolExecutor
THREADPOOL = ThreadPoolExecutor(max_workers=1000)
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')




bot = Client(
    "techvjbot",
    api_id=api_id,
    api_hash=api_hash,
    bot_token=bot_token
)

@bot.on_message(filters.command(["start"]))
async def start(bot, message):
    await message.reply_text(text="**🎉 Bot Is Running... 🚀**\n\n**🧑‍💻 Start Bot Using /help**")

@bot.on_message(filters.command(["help"]))
async def help(bot, message):
    keyboard = [[
        InlineKeyboardButton("🚀 Physics Wallah Without Purchase 🚀", callback_data="pwwp")
    ],[
        InlineKeyboardButton("📘 Classplus Without Purchase 📘", callback_data="cpwp")
    ],[
        InlineKeyboardButton("📒 Appx Without Purchase 📒", callback_data="appxwp")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text(
        text="**📌 Choose Your Button From Below 👇**",
        reply_markup=reply_markup
    )



        
async def fetch_pwwp_data(session: aiohttp.ClientSession, url: str, headers: Dict = None, params: Dict = None, data: Dict = None, method: str = 'GET') -> Any:
    max_retries = 3
    for attempt in range(max_retries):
        try:
            async with session.request(method, url, headers=headers, params=params, json=data) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientError as e:
            logging.error(f"Attempt {attempt + 1} failed: aiohttp error fetching {url}: {e}")
        except Exception as e:
            logging.exception(f"Attempt {attempt + 1} failed: Unexpected error fetching {url}: {e}")

        if attempt < max_retries - 1:
            await asyncio.sleep(90 ** attempt)
        else:
            logging.error(f"Failed to fetch {url} after {max_retries} attempts.")
            return None



async def process_pwwp_chapter_content(session: aiohttp.ClientSession, chapter_id, selected_batch_id, subject_id, schedule_id, content_type, headers: Dict):
    url = f"https://api.penpencil.co/v1/batches/{selected_batch_id}/subject/{subject_id}/schedule/{schedule_id}/schedule-details"
    data = await fetch_pwwp_data(session, url, headers=headers)
    content = []

    if data and data.get("success") and data.get("data"):
        data_item = data["data"]

        if content_type in ("videos", "DppVideos"):
            video_details = data_item.get('videoDetails', {})
            videoUrl = ""
            if video_details:
                name = data_item.get('topic', '')
                # Try multiple field names for video URL
                videoUrl = (
                    video_details.get('videoUrl')
                    or video_details.get('embedCode')
                    or video_details.get('mediaUrl')
                    or video_details.get('streamUrl')
                    or video_details.get('hlsUrl')
                    or video_details.get('mpdUrl')
                    or video_details.get('downloadUrl')
                    or video_details.get('url')
                    or video_details.get('fileUrl')
                    or ""
                )
                
                # If embedCode is HTML (iframe), try to extract URL from it
                if videoUrl and ('<' in videoUrl or 'iframe' in videoUrl.lower() or 'src=' in videoUrl.lower()):
                    import re as re_extract
                    src_match = re_extract.search(r'src=["\'](https?://[^"\']+)["\']', videoUrl)
                    if src_match:
                        videoUrl = src_match.group(1)
                    else:
                        # Try to find any URL in the embed code
                        url_match = re_extract.search(r'https?://[^"\'\s<>]+', videoUrl)
                        if url_match:
                            videoUrl = url_match.group(0)
                
                # Also check if videoUrl is directly in data_item (not nested)
                if not videoUrl:
                    videoUrl = (
                        data_item.get('videoUrl')
                        or data_item.get('mediaUrl')
                        or data_item.get('streamUrl')
                        or data_item.get('hlsUrl')
                        or data_item.get('mpdUrl')
                        or data_item.get('url')
                        or ""
                    )

                if videoUrl:
                    line = f"{name}:{videoUrl}"
                    content.append(line)
                    
            # Also check homeworkIds for video-type attachments
            if not videoUrl:
                homework_ids = data_item.get('homeworkIds', [])
                for homework in homework_ids:
                    attachment_ids = homework.get('attachmentIds', [])
                    name = homework.get('topic', '')
                    for attachment in attachment_ids:
                        url = attachment.get('baseUrl', '') + attachment.get('key', '')
                        if url and not url.endswith('.pdf'):
                            line = f"{name}:{url}"
                            content.append(line)

        elif content_type in ("notes", "DppNotes"):
            homework_ids = data_item.get('homeworkIds', [])
            for homework in homework_ids:
                attachment_ids = homework.get('attachmentIds', [])
                name = homework.get('topic', '')
                for attachment in attachment_ids:
                    url = attachment.get('baseUrl', '') + attachment.get('key', '')
                    if url:
                        line = f"{name}:{url}"
                        content.append(line)

        return {content_type: content} if content else {}
    else:
        logging.warning(f"No Data Found For  Id - {schedule_id}")
        return {}




async def fetch_pwwp_all_schedule(session: aiohttp.ClientSession, chapter_id, selected_batch_id, subject_id, content_type, headers: Dict) -> List[Dict]:
    all_schedule = []
    page = 1
    while True:
        params = {
            'tag': chapter_id,
            'contentType': content_type,
            'page': page
        }
        url = f"https://api.penpencil.co/v2/batches/{selected_batch_id}/subject/{subject_id}/contents"
        data = await fetch_pwwp_data(session, url, headers=headers, params=params)

        if data and data.get("success") and data.get("data"):
            for item in data["data"]:
                item['content_type'] = content_type
                # Try to extract video URL directly from contents response
                # (some API versions include it here without needing schedule-details call)
                if content_type in ("videos", "DppVideos"):
                    direct_url = (
                        item.get('videoUrl')
                        or item.get('mediaUrl')
                        or (item.get('videoDetails') or {}).get('videoUrl')
                        or (item.get('videoDetails') or {}).get('embedCode')
                        or (item.get('videoDetails') or {}).get('url')
                    )
                    if direct_url:
                        item['_pre_extracted_url'] = direct_url
                all_schedule.append(item)
            page += 1
        else:
            break
    return all_schedule




async def process_pwwp_chapters(session: aiohttp.ClientSession, chapter_id, selected_batch_id, subject_id, headers: Dict):
    content_types = ['videos', 'notes', 'DppNotes', 'DppVideos']
    
    all_schedule_tasks = [fetch_pwwp_all_schedule(session, chapter_id, selected_batch_id, subject_id, content_type, headers) for content_type in content_types]
    all_schedules = await asyncio.gather(*all_schedule_tasks)
    
    all_schedule = []
    for schedule in all_schedules:
        all_schedule.extend(schedule)
        
    content_tasks = []
    for item in all_schedule:
        schedule_id = item["_id"]
        ct = item['content_type']
        # If we already got the URL from contents API, use it directly
        if ct in ("videos", "DppVideos") and item.get('_pre_extracted_url'):
            # Create a simple task that returns the URL directly
            async def _direct(sid=schedule_id, ct=ct, url=item['_pre_extracted_url']):
                return {ct: [f"{sid}:{url}"]}
            content_tasks.append(_direct())
        else:
            content_tasks.append(
                process_pwwp_chapter_content(session, chapter_id, selected_batch_id, subject_id, schedule_id, ct, headers)
            )
    content_results = await asyncio.gather(*content_tasks)

    combined_content = {}
    for result in content_results:
        if result:
            for content_type, content_list in result.items():
                if content_type not in combined_content:
                    combined_content[content_type] = []
                combined_content[content_type].extend(content_list)

    return combined_content




async def get_pwwp_all_chapters(session: aiohttp.ClientSession, selected_batch_id, subject_id, headers: Dict):
    all_chapters = []
    page = 1
    while True:
        url = f"https://api.penpencil.co/v2/batches/{selected_batch_id}/subject/{subject_id}/topics?page={page}"
        data = await fetch_pwwp_data(session, url, headers=headers)

        if data and data.get("data"):
            chapters = data["data"]
            all_chapters.extend(chapters)
            page += 1
        else:
            break

    return all_chapters

# Don't Remove Credit Tg - @VJ_Bots
# Subscribe YouTube Channel For Amazing Bot @Tech_VJ
# Ask Doubt on telegram @KingVJ01


async def process_pwwp_subject(session: aiohttp.ClientSession, subject: Dict, selected_batch_id: str, selected_batch_name: str, zipf: zipfile.ZipFile, json_data: Dict, all_subject_urls: Dict[str, List[str]], headers: Dict):
    subject_name = subject.get("subject", "Unknown Subject").replace("/", "-")
    subject_id = subject.get("_id")
    json_data[selected_batch_name][subject_name] = {}
    zipf.writestr(f"{subject_name}/", "")
    
    chapters = await get_pwwp_all_chapters(session, selected_batch_id, subject_id, headers)
    
    chapter_tasks = []
    for chapter in chapters:
        chapter_name = chapter.get("name", "Unknown Chapter").replace("/", "-")
        zipf.writestr(f"{subject_name}/{chapter_name}/", "")
        json_data[selected_batch_name][subject_name][chapter_name] = {}

        chapter_tasks.append(process_pwwp_chapters(session, chapter["_id"], selected_batch_id, subject_id, headers))

    chapter_results = await asyncio.gather(*chapter_tasks)

    all_urls = []
    for chapter, chapter_content in zip(chapters, chapter_results):
        chapter_name = chapter.get("name", "Unknown Chapter").replace("/", "-")

        for content_type in ['videos', 'notes', 'DppNotes', 'DppVideos']:
            if chapter_content.get(content_type):
                content = chapter_content[content_type]
                content.reverse()
                content_string = "\n".join(content)
                zipf.writestr(f"{subject_name}/{chapter_name}/{content_type}.txt", content_string.encode('utf-8'))
                json_data[selected_batch_name][subject_name][chapter_name][content_type] = content
                all_urls.extend(content)
    all_subject_urls[subject_name] = all_urls



def find_pw_old_batch(batch_search):

    try:
        response = requests.get(f"https://abhiguru143.github.io/AS-MULTIVERSE-PW/batch/batch.json")
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching data: {e}")
        return []
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON: {e}")
        return []

    matching_batches = []
    for batch in data:
        if batch_search.lower() in batch['batch_name'].lower():
            matching_batches.append(batch)

    return matching_batches



async def get_pwwp_todays_schedule_content_details(session: aiohttp.ClientSession, selected_batch_id, subject_id, schedule_id, headers: Dict) -> List[str]:

    url = f"https://api.penpencil.co/v1/batches/{selected_batch_id}/subject/{subject_id}/schedule/{schedule_id}/schedule-details"
    data = await fetch_pwwp_data(session, url, headers)
    content = []

    if data and data.get("success") and data.get("data"):
        data_item = data["data"]
        
        video_details = data_item.get('videoDetails', {})
        videoUrl = ""
        if video_details:
            name = data_item.get('topic')
            
            videoUrl = (
                video_details.get('videoUrl')
                or video_details.get('embedCode')
                or video_details.get('mediaUrl')
                or video_details.get('streamUrl')
                or video_details.get('hlsUrl')
                or video_details.get('mpdUrl')
                or video_details.get('downloadUrl')
                or video_details.get('url')
                or video_details.get('fileUrl')
                or ""
            )
            
            # If embedCode is HTML, extract URL
            if videoUrl and ('<' in videoUrl or 'iframe' in videoUrl.lower() or 'src=' in videoUrl.lower()):
                import re as re_extract
                src_match = re_extract.search(r'src=["\'](https?://[^"\']+)["\']', videoUrl)
                if src_match:
                    videoUrl = src_match.group(1)
                else:
                    url_match = re_extract.search(r'https?://[^"\'\s<>]+', videoUrl)
                    if url_match:
                        videoUrl = url_match.group(0)
            
            # Also check data_item
            if not videoUrl:
                videoUrl = (
                    data_item.get('videoUrl')
                    or data_item.get('mediaUrl')
                    or data_item.get('streamUrl')
                    or data_item.get('hlsUrl')
                    or data_item.get('mpdUrl')
                    or data_item.get('url')
                    or ""
                )
                
            if videoUrl:
                line = f"{name}:{videoUrl}\n"
                content.append(line)
        
        # Also check homeworkIds for non-pdf attachments (videos)
        if not videoUrl:
            homework_ids = data_item.get('homeworkIds')
            for homework in homework_ids or []:
                attachment_ids = homework.get('attachmentIds')
                name = homework.get('topic')
                for attachment in attachment_ids or []:
                    url = attachment.get('baseUrl', '') + attachment.get('key', '')
                    if url and not url.endswith('.pdf'):
                        line = f"{name}:{url}\n"
                        content.append(line)
                
        dpp = data_item.get('dpp')
        if dpp:
            dpp_homework_ids = dpp.get('homeworkIds')
            for homework in dpp_homework_ids:
                attachment_ids = homework.get('attachmentIds')
                name = homework.get('topic')
                for attachment in attachment_ids:
                
                    url = attachment.get('baseUrl', '') + attachment.get('key', '')
                        
                    if url:
                        line = f"{name}:{url}\n"
                        content.append(line)
                    #    logging.info(line)
    else:
        logging.warning(f"No Data Found For  Id - {schedule_id}")
    return content



async def get_pwwp_all_todays_schedule_content(session: aiohttp.ClientSession, selected_batch_id: str, headers: Dict) -> List[str]:

    url = f"https://api.penpencil.co/v1/batches/{selected_batch_id}/todays-schedule"
    todays_schedule_details = await fetch_pwwp_data(session, url, headers)
    all_content = []

    if todays_schedule_details and todays_schedule_details.get("success") and todays_schedule_details.get("data"):
        tasks = []

        for item in todays_schedule_details['data']:
            schedule_id = item.get('_id')
            subject_id = item.get('batchSubjectId')
            
            task = asyncio.create_task(get_pwwp_todays_schedule_content_details(session, selected_batch_id, subject_id, schedule_id, headers))
            tasks.append(task)
            
        results = await asyncio.gather(*tasks)
        
        for result in results:
            all_content.extend(result)
            
    else:
        logging.warning("No today's schedule data found.")

    return all_content


    
@bot.on_callback_query(filters.regex("^pwwp$"))
async def pwwp_callback(bot, callback_query):
    user_id = callback_query.from_user.id
    await callback_query.answer()
    
    auth_user = auth_users[0]
    user = await bot.get_users(auth_user)
    owner_username = "@durov" 

    if user_id not in auth_users:
        await bot.send_message(callback_query.message.chat.id, f"**You Are Not Subscribed To This Bot\nContact - {owner_username}**")
        return
            
    THREADPOOL.submit(asyncio.run, process_pwwp(bot, callback_query.message, user_id))

# Don't Remove Credit Tg - @VJ_Bots
# Subscribe YouTube Channel For Amazing Bot @Tech_VJ
# Ask Doubt on telegram @KingVJ01

async def process_pwwp(bot: Client, m: Message, user_id: int):

    editable = await m.reply_text("**Enter Woking Access Token\n\nOR\n\nEnter Phone Number**")

    try:
        input1 = await bot.listen(chat_id=m.chat.id, filters=filters.user(user_id), timeout=120)
        raw_text1 = input1.text
        await input1.delete(True)
    except:
        await editable.edit("**Timeout! You took too long to respond**")
        return

    headers = {
        'Host': 'api.penpencil.co',
        'client-id': '5eb393ee95fab7468a79d189',
        'client-version': '1910',
        'user-agent': 'Mozilla/5.0 (Linux; Android 12; M2101K6P) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Mobile Safari/537.36',
        'randomid': '72012511-256c-4e1c-b4c7-29d67136af37',
        'client-type': 'WEB',
        'content-type': 'application/json; charset=utf-8',
    }

    loop = asyncio.get_event_loop()    
    CONNECTOR = aiohttp.TCPConnector(limit=1000, loop=loop)
    async with aiohttp.ClientSession(connector=CONNECTOR, loop=loop) as session:
        try:
            if raw_text1.isdigit() and len(raw_text1) == 10:
                phone = raw_text1
                data = {
                    "username": phone,
                    "countryCode": "+91",
                    "organizationId": "5eb393ee95fab7468a79d189"
                }
                try:
                    async with session.post(f"https://api.penpencil.co/v1/users/get-otp?smsType=0", json=data, headers=headers) as response:
                        await response.read()
                    
                except Exception as e:
                    await editable.edit(f"**Error : {e}**")
                    return

                editable = await editable.edit("**ENTER OTP YOU RECEIVED**")
                try:
                    input2 = await bot.listen(chat_id=m.chat.id, filters=filters.user(user_id), timeout=120)
                    otp = input2.text
                    await input2.delete(True)
                except:
                    await editable.edit("**Timeout! You took too long to respond**")
                    return

                payload = {
                    "username": phone,
                    "otp": otp,
                    "client_id": "system-admin",
                    "client_secret": "KjPXuAVfC5xbmgreETNMaL7z",
                    "grant_type": "password",
                    "organizationId": "5eb393ee95fab7468a79d189",
                    "latitude": 0,
                    "longitude": 0
                }

                try:
                    async with session.post(f"https://api.penpencil.co/v3/oauth/token", json=payload, headers=headers) as response:
                        access_token = (await response.json())["data"]["access_token"]
                        monster = await editable.edit(f"<b>Physics Wallah Login Successful ✅</b>\n\n<pre language='Save this Login Token for future usage'>{access_token}</pre>\n\n")
                        editable = await m.reply_text("**Getting Batches In Your I'd**")
                    
                except Exception as e:
                    await editable.edit(f"**Error : {e}**")
                    return

            else:
                access_token = raw_text1
            
            headers['authorization'] = f"Bearer {access_token}"
        
            params = {
                'mode': '1',
                'page': '1',
            }
            try:
                async with session.get(f"https://api.penpencil.co/v3/batches/all-purchased-batches", headers=headers, params=params) as response:
                    response.raise_for_status()
                    batches = (await response.json()).get("data", [])
            except Exception as e:
                await editable.edit("**```\nLogin Failed❗TOKEN IS EXPIRED```\nPlease Enter Working Token\n                       OR\nLogin With Phone Number**")
                return
        
            await editable.edit("**Enter Your Batch Name**")
            try:
                input3 = await bot.listen(chat_id=m.chat.id, filters=filters.user(user_id), timeout=120)
                batch_search = input3.text
                await input3.delete(True)
            except:
                await editable.edit("**Timeout! You took too long to respond**")
                return
                
            url = f"https://api.penpencil.co/v3/batches/search?name={batch_search}"
            courses = await fetch_pwwp_data(session, url, headers)
            courses = courses.get("data", {}) if courses else {}

            if courses:
                text = ''
                for cnt, course in enumerate(courses):
                    name = course['name']
                    text += f"{cnt + 1}. ```\n{name}```\n"
                await editable.edit(f"**Send index number of the course to download.\n\n{text}\n\nIf Your Batch Not Listed Above Enter - No**")
            
                try:
                    input4 = await bot.listen(chat_id=m.chat.id, filters=filters.user(user_id), timeout=120)
                    raw_text4 = input4.text
                    await input4.delete(True)
                except:
                    await editable.edit("**Timeout! You took too long to respond**")
                    return
                
                if input4.text.isdigit() and 1 <= int(input4.text) <= len(courses):
                    selected_course_index = int(input4.text.strip())
                    course = courses[selected_course_index - 1]
                    selected_batch_id = course['_id']
                    selected_batch_name = course['name']
                    clean_batch_name = selected_batch_name.replace("/", "-").replace("|", "-")
                    clean_file_name = f"{user_id}_{clean_batch_name}"
                    
                elif "No" in input4.text:
                    courses = find_pw_old_batch(batch_search)
                    if courses:
                        text = ''
                        for cnt, course in enumerate(courses):
                            name = course['batch_name']
                            text += f"{cnt + 1}. ```\n{name}```\n"
                            
                        await editable.edit(f"**Send index number of the course to download.\n\n{text}**")
                
                        try:
                            input5 = await bot.listen(chat_id=m.chat.id, filters=filters.user(user_id), timeout=120)
                            raw_text5 = input5.text
                            await input5.delete(True)
                        except:
                            await editable.edit("**Timeout! You took too long to respond**")
                            return
                
                        if input5.text.isdigit() and 1 <= int(input5.text) <= len(courses):
                            selected_course_index = int(input5.text.strip())
                            course = courses[selected_course_index - 1]
                            selected_batch_id = course['batch_id']
                            selected_batch_name = course['batch_name']
                            clean_batch_name = selected_batch_name.replace("/", "-").replace("|", "-")
                            clean_file_name = f"{user_id}_{clean_batch_name}"
                        else:
                            raise Exception("Invalid batch index.")
                else:
                    raise Exception("Invalid batch index.")
                    
                await editable.edit("1.```\nFull Batch```\n2.```\nToday's Class```\n3.```\nKhazana```")
                    
                try:
                    input6 = await bot.listen(chat_id=m.chat.id, filters=filters.user(user_id), timeout=120)
                    raw_text6 = input6.text
                    await input6.delete(True)
                except ListenerTimeout:
                    await editable.edit("**Timeout! You took too long to respond**")
                    return
                except Exception as e:
                    logging.exception("Error during option listening:")
                    try:
                        await editable.edit(f"**Error: {e}**")
                    except:
                        logging.error(f"Failed to send error message to user: {e}")
                    return
                        
                await editable.edit(f"**Extracting course : {selected_batch_name} ...**")

                start_time = time.time()

                if input6.text == '1':
                
                    url = f"https://api.penpencil.co/v3/batches/{selected_batch_id}/details"
                    batch_details = await fetch_pwwp_data(session, url, headers=headers)

                    if batch_details and batch_details.get("success"):
                        subjects = batch_details.get("data", {}).get("subjects", [])

                        json_data = {selected_batch_name: {}}
                        all_subject_urls = {}

                        with zipfile.ZipFile(f"{clean_file_name}.zip", 'w') as zipf:
                            
                            subject_tasks = [process_pwwp_subject(session, subject, selected_batch_id, selected_batch_name, zipf, json_data, all_subject_urls, headers) for subject in subjects]
                            await asyncio.gather(*subject_tasks)
                        
                        with open(f"{clean_file_name}.json", 'w') as f:
                            json.dump(json_data, f, indent=4)
                            
                        with open(f"{clean_file_name}.txt", 'w', encoding='utf-8') as f:
                            for subject in subjects:
                                subject_name = subject.get("subject", "Unknown Subject").replace("/", "-")
                                if subject_name in all_subject_urls:
                                    f.write('\n'.join(all_subject_urls[subject_name]) + '\n')

                    else:
                        raise Exception(f"Error fetching batch details: {batch_details.get('message')}")
                    
                elif input6.text == '2':
                    
                    selected_batch_name = "Today's Class"
                    today_schedule = await get_pwwp_all_todays_schedule_content(session, selected_batch_id, headers)
                    if today_schedule:
                        with open(f"{clean_file_name}.txt", "w", encoding="utf-8") as f:
                            f.writelines(today_schedule)
                    else:
                        raise Exception("No Classes Found Today")
                        
                elif input6.text == '3':
                    raise Exception("Working In Progress")
                    
                else:
                    raise Exception("Invalid index.")
                    
                end_time = time.time()
                response_time = end_time - start_time
                minutes = int(response_time // 60)
                seconds = int(response_time % 60)

                if minutes == 0:
                    if seconds < 1:
                        formatted_time = f"{response_time:.2f} seconds"
                    else:
                        formatted_time = f"{seconds} seconds"
                else:
                    formatted_time = f"{minutes} minutes {seconds} seconds"
                            
                await editable.delete(True)
                
                caption = f"**Batch Name : ```\n{selected_batch_name}``````\nTime Taken : {formatted_time}```**"
                        
                files = [f"{clean_file_name}.{ext}" for ext in ["txt", "zip", "json"]]
                for file in files:
                    file_ext = os.path.splitext(file)[1][1:]
                    try:
                        with open(file, 'rb') as f:
                            doc = await m.reply_document(document=f, caption=caption, file_name=f"{clean_batch_name}.{file_ext}")
                    except FileNotFoundError:
                        logging.error(f"File not found: {file}")
                    except Exception as e:
                        logging.exception(f"Error sending document {file}:")
                    finally:
                        try:
                            os.remove(file)
                            logging.info(f"Removed File After Sending : {file}")
                        except OSError as e:
                            logging.error(f"Error deleting {file}: {e}")
            else:
                raise Exception("No batches found for the given search name.")
                
        except Exception as e:
            logging.exception(f"An unexpected error occurred: {e}")
            try:
                await editable.edit(f"**Error : {e}**")
            except Exception as ee:
                logging.error(f"Failed to send error message to user in callback: {ee}")
        finally:
            if session:
                await session.close()
            await CONNECTOR.close()


            
async def fetch_cpwp_signed_url(url_val: str, name: str, session: aiohttp.ClientSession, headers: Dict[str, str]) -> str | None:
    MAX_RETRIES = 3
    for attempt in range(MAX_RETRIES):
        params = {"url": url_val}
        try:
            async with session.get("https://api.classplusapp.com/cams/uploader/video/jw-signed-url", params=params, headers=headers) as response:
                response.raise_for_status()
                response_json = await response.json()
                signed_url = response_json.get("url") or response_json.get('drmUrls', {}).get('manifestUrl')
                return signed_url
                
        except Exception as e:
         #   logging.exception(f"Unexpected error fetching signed URL for {name}: {e}. Attempt {attempt + 1}/{MAX_RETRIES}")
            pass

        if attempt < MAX_RETRIES - 1:
            await asyncio.sleep(2 ** attempt)

    logging.error(f"Failed to fetch signed URL for {name} after {MAX_RETRIES} attempts.")
    return None



async def process_cpwp_url(url_val: str, name: str, session: aiohttp.ClientSession, headers: Dict[str, str]) -> str | None:
    try:
        signed_url = await fetch_cpwp_signed_url(url_val, name, session, headers)
        if not signed_url:
            logging.warning(f"Failed to obtain signed URL for {name}: {url_val}")
            return None

        if "testbook.com" in url_val or "classplusapp.com/drm" in url_val or "media-cdn.classplusapp.com/drm" in url_val:
        #    logging.info(f"{name}:{url_val}")
            return f"{name}:{url_val}\n"

        async with session.get(signed_url) as response:
            response.raise_for_status()
       #     logging.info(f"{name}:{url_val}")
            return f"{name}:{url_val}\n"
            
    except Exception as e:
    #    logging.exception(f"Unexpected error processing {name}: {e}")
        pass
    return None



async def get_cpwp_course_content(session: aiohttp.ClientSession, headers: Dict[str, str], Batch_Token: str, folder_id: int = 0, limit: int = 9999999999, retry_count: int = 0) -> Tuple[List[str], int, int, int]:
    MAX_RETRIES = 3
    fetched_urls: set[str] = set()
    results: List[str] = []
    video_count = 0
    pdf_count = 0
    image_count = 0
    content_tasks: List[Tuple[int, asyncio.Task[str | None]]] = []
    folder_tasks: List[Tuple[int, asyncio.Task[List[str]]]] = []

    try:
        content_api = f'https://api.classplusapp.com/v2/course/preview/content/list/{Batch_Token}'
        params = {'folderId': folder_id, 'limit': limit}

        async with session.get(content_api, params=params, headers=headers) as res:
            res.raise_for_status()
            res_json = await res.json()
            contents: List[Dict[str, Any]] = res_json['data']

            for content in contents:
                if content['contentType'] == 1:
                    folder_task = asyncio.create_task(get_cpwp_course_content(session, headers, Batch_Token, content['id'], retry_count=0))
                    folder_tasks.append((content['id'], folder_task))

                else:
                    name: str = content['name']
                    url_val: str | None = content.get('url') or content.get('thumbnailUrl')

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
                        url_val = f'https://media-cdn.classplusapp.com/alisg-cdn-a.classplusapp.com/b08bad9ff8d969639b2e43d5769342cc62b510c4345d2f7f153bec53be84fe35/{url_val.split('/')[-1].split('.')[0]}/master.m3u8'
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
                        headers2 = { 'x-access-token': 'eyJjb3Vyc2VJZCI6IjQ1NjY4NyIsInR1dG9ySWQiOm51bGwsIm9yZ0lkIjo0ODA2MTksImNhdGVnb3J5SWQiOm51bGx9'}
                        task = asyncio.create_task(process_cpwp_url(url_val, name, session, headers2))
                        content_tasks.append((content['id'], task))
                        
                    else:
                        name: str = content['name']
                        url_val: str | None = content.get('url')
                        if url_val:
                            fetched_urls.add(url_val)
                        #    logging.info(f"{name}:{url_val}")
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
            return await get_cpwp_course_content(session, headers, Batch_Token, folder_id, limit, retry_count + 1)
        else:
            logging.error(f"Failed to retrieve folder {folder_id} after {MAX_RETRIES} retries.")
            return [], 0, 0, 0
            
    content_results = await asyncio.gather(*(task for _, task in content_tasks), return_exceptions=True)
    folder_results = await asyncio.gather(*(task for _, task in folder_tasks), return_exceptions=True)
    
    for (folder_id, result) in zip(content_tasks, content_results):
        if isinstance(result, Exception):
            logging.error(f"Task failed with exception: {result}")
        elif result:
            results.append(result)
            video_count += 1
            
    for folder_id, folder_result in folder_tasks:
        try:
            nested_results, nested_video_count, nested_pdf_count, nested_image_count = await folder_result
            if nested_results:
                results.extend(nested_results)
            else:
            #    logging.warning(f"get_cpwp_course_content returned None for folder_id {folder_id}")
                pass
            video_count += nested_video_count
            pdf_count += nested_pdf_count
            image_count += nested_image_count
        except Exception as e:
            logging.error(f"Error processing folder {folder_id}: {e}")

    return results, video_count, pdf_count, image_count



@bot.on_callback_query(filters.regex("^cpwp$"))
async def cpwp_callback(bot, callback_query):
    user_id = callback_query.from_user.id
    await callback_query.answer()

    auth_user = auth_users[0]
    user = await bot.get_users(auth_user)
    owner_username = "@durov" 

    if user_id not in auth_users:
        await bot.send_message(callback_query.message.chat.id, f"**You Are Not Subscribed To This Bot\nContact - {owner_username}**")
        return    
            
    THREADPOOL.submit(asyncio.run, process_cpwp(bot, callback_query.message, user_id))


# Don't Remove Credit Tg - @VJ_Bots
# Subscribe YouTube Channel For Amazing Bot @Tech_VJ
# Ask Doubt on telegram @KingVJ01

async def process_cpwp(bot: Client, m: Message, user_id: int):
    
    headers = {
        'accept-encoding': 'gzip',
        'accept-language': 'EN',
        'api-version'    : '35',
        'app-version'    : '1.4.73.2',
        'build-number'   : '35',
        'connection'     : 'Keep-Alive',
        'content-type'   : 'application/json',
        'device-details' : 'Xiaomi_Redmi 7_SDK-32',
        'device-id'      : 'c28d3cb16bbdac01',
        'host'           : 'api.classplusapp.com',
        'region'         : 'IN',
        'user-agent'     : 'Mobile-Android',
        'webengage-luid' : '00000187-6fe4-5d41-a530-26186858be4c'
    }

    loop = asyncio.get_event_loop()
    CONNECTOR = aiohttp.TCPConnector(limit=1000, loop=loop)
    async with aiohttp.ClientSession(connector=CONNECTOR, loop=loop) as session:
        try:
            editable = await m.reply_text("**Enter ORG Code Of Your Classplus App**")
            
            try:
                input1 = await bot.listen(chat_id=m.chat.id, filters=filters.user(user_id), timeout=120)
                org_code = input1.text.lower()
                await input1.delete(True)
            except ListenerTimeout:
                await editable.edit("**Timeout! You took too long to respond**")
                return
            except Exception as e:
                logging.exception("Error during input1 listening:")
                try:
                    await editable.edit(f"**Error: {e}**")
                except:
                    logging.error(f"Failed to send error message to user: {e}")
                return

            hash_headers = {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'Accept-Encoding': 'gzip, deflate, br, zstd',
                'Accept-Language': 'en-US,en;q=0.9',
                'Referer': 'https://qsvfn.courses.store/?mainCategory=0&subCatList=[130504,62442]',
                'Sec-CH-UA': '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
                'Sec-CH-UA-Mobile': '?0',
                'Sec-CH-UA-Platform': '"Windows"',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'same-origin',
                'Sec-Fetch-User': '?1',
                'Upgrade-Insecure-Requests': '1',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36'
            }
            
            async with session.get(f"https://{org_code}.courses.store", headers=hash_headers) as response:
                html_text = await response.text()
                hash_match = re.search(r'"hash":"(.*?)"', html_text)

                if hash_match:
                    token = hash_match.group(1)
                    
                    async with session.get(f"https://api.classplusapp.com/v2/course/preview/similar/{token}?limit=20", headers=headers) as response:
                        if response.status == 200:
                            res_json = await response.json()
                            courses = res_json.get('data', {}).get('coursesData', [])

                            if courses:
                                text = ''
                                for cnt, course in enumerate(courses):
                                    name = course['name']
                                    price = course['finalPrice']
                                    text += f'{cnt + 1}. ```\n{name} 💵₹{price}```\n'

                                await editable.edit(f"**Send index number of the Category Name\n\n{text}\nIf Your Batch Not Listed Then Enter Your Batch Name**")
                            
                                try:
                                    input2 = await bot.listen(chat_id=m.chat.id, filters=filters.user(user_id), timeout=120)
                                    raw_text2 = input2.text
                                    await input2.delete(True)
                                except ListenerTimeout:
                                    await editable.edit("**Timeout! You took too long to respond**")
                                    return
                                except Exception as e:
                                    logging.exception("Error during input1 listening:")
                                    try:
                                        await editable.edit(f"**Error : {e}**")
                                    except:
                                        logging.error(f"Failed to send error message to user : {e}")
                                    return

                                if input2.text.isdigit() and len(input2.text) <= len(courses):
                                    selected_course_index = int(input2.text.strip())
                                    course = courses[selected_course_index - 1]
                                    selected_batch_id = course['id']
                                    selected_batch_name = course['name']
                                    price = course['finalPrice']
                                    clean_batch_name = selected_batch_name.replace("/", "-").replace("|", "-")
                                    clean_file_name = f"{user_id}_{clean_batch_name}"

                                else:
                                    search_url = f"https://api.classplusapp.com/v2/course/preview/similar/{token}?search={raw_text2}"
                                    async with session.get(search_url, headers=headers) as response:
                                        if response.status == 200:
                                            res_json = await response.json()
                                            courses = res_json.get("data", {}).get("coursesData", [])

                                            if courses:
                                                text = ''
                                                for cnt, course in enumerate(courses):
                                                    name = course['name']
                                                    price = course['finalPrice']
                                                    text += f'{cnt + 1}. ```\n{name} 💵₹{price}```\n'
                                                await editable.edit(f"**Send index number of the Batch to download.\n\n{text}**")
                                            
                                                try:
                                                    input3 = await bot.listen(chat_id=m.chat.id, filters=filters.user(user_id), timeout=120)
                                                    raw_text3 = input3.text
                                                    await input3.delete(True)
                                                except ListenerTimeout:
                                                    await editable.edit("**Timeout! You took too long to respond**")
                                                    return
                                                except Exception as e:
                                                    logging.exception("Error during input1 listening:")
                                                    try:
                                                        await editable.edit(f"**Error : {e}**")
                                                    except:
                                                        logging.error(f"Failed to send error message to user : {e}")
                                                    return


                                                if input3.text.isdigit() and len(input3.text) <= len(courses):
                                                    selected_course_index = int(input3.text.strip())
                                                    course = courses[selected_course_index - 1]
                                                    selected_batch_id = course['id']
                                                    selected_batch_name = course['name']
                                                    price = course['finalPrice']
                                                    clean_batch_name = selected_batch_name.replace("/", "-").replace("|", "-")
                                                    clean_file_name = f"{user_id}_{clean_batch_name}"
                                                
                                                else:
                                                    raise Exception("Wrong Index Number")
                                            else:
                                                raise Exception("Didn't Find Any Course Matching The Search Term")
                                        else:
                                            raise Exception(f"{response.text}")
                                            
                                download_price = int(price * 0.10)
                                batch_headers = {
                                    'Accept': 'application/json, text/plain, */*',
                                    'region': 'IN',
                                    'accept-language': 'EN',
                                    'Api-Version': '22',
                                    'tutorWebsiteDomain': f'https://{org_code}.courses.store'
                                }
                                    
                                params = {
                                    'courseId': f'{selected_batch_id}',
                                }

                                async with session.get(f"https://api.classplusapp.com/v2/course/preview/org/info", params=params, headers=batch_headers) as response:
                                    if response.status == 200:
                                        res_json = await response.json()
                                        Batch_Token = res_json['data']['hash']
                                        App_Name = res_json['data']['name']

                                        await editable.edit(f"**Extracting course : {selected_batch_name} ...**")

                                        start_time = time.time()
                                        course_content, video_count, pdf_count, image_count = await get_cpwp_course_content(session, headers, Batch_Token)
                                    
                                        if course_content:
                                            file = f"{clean_file_name}.txt"

                                            with open(file, 'w') as f:
                                                f.write(''.join(course_content))

                                            end_time = time.time()
                                            response_time = end_time - start_time
                                            minutes = int(response_time // 60)
                                            seconds = int(response_time % 60)

                                            if minutes == 0:
                                                if seconds < 1:
                                                    formatted_time = f"{response_time:.2f} seconds"
                                                else:
                                                    formatted_time = f"{seconds} seconds"
                                            else:
                                                formatted_time = f"{minutes} minutes {seconds} seconds"

                                            await editable.delete(True)
                                        
                                            caption = f"**App Name : ```\n{App_Name}({org_code})```\nBatch Name : ```\n{selected_batch_name}``````\n🎬 : {video_count} | 📁 : {pdf_count} | 🖼  : {image_count}``````\nTime Taken : {formatted_time}```**"
                                        
                                            with open(file, 'rb') as f:
                                                doc = await m.reply_document(document=f, caption=caption, file_name=f"{clean_batch_name}.txt")

                                            os.remove(file)

                                        else:
                                            raise Exception("Didn't Find Any Content In The Course")
                                    else:
                                        raise Exception(f"{response.text}")
                            else:
                                raise Exception("Didn't Find Any Course")
                        else:
                            raise Exception(f"{response.text}")
                else:
                    raise Exception('No App Found In Org Code')
                    
        except Exception as e:
            await editable.edit(f"**Error : {e}**")
            
        finally:
            await session.close()
            await CONNECTOR.close()





def appx_decrypt(enc):
    enc = b64decode(enc.split(':')[0])
    key = '638udh3829162018'.encode('utf-8')
    iv = 'fedcba9876543210'.encode('utf-8')

    if len(enc) == 0:
        return ""

    cipher = AES.new(key, AES.MODE_CBC, iv)
    plaintext = unpad(cipher.decrypt(enc), AES.block_size)
    b = plaintext.decode('utf-8')
    url = b
    return url




async def fetch_appx_html_to_json(session, url, headers=None, data=None):
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
                try:
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
                    else:
                        logging.error("Could not find matching closing brace } . json string: ", json_str)
                        return None
                except json.JSONDecodeError:
                    logging.error("Could not parse JSON from the end. ", json_str)
                    return None
            else:
                logging.error("Could not find JSON at the end. Response content: ", text)
                return None
    except Exception as e:
        logging.exception(f"An error occurred during the request: {e}")
        return None



async def fetch_appx_video_id_details_v2(session, api, selected_batch_id, video_id, ytFlag, headers, folder_wise_course, user_id):
    logging.info(f"User ID: {user_id} - Fetching video details for video ID: {video_id}")
    try:
        # 🚨 FIXED: Try without auth if auth headers fail
        headers_noauth = {k: v for k, v in headers.items() if k.lower() not in ('authorization', 'user-id')}
        
        res = await fetch_appx_html_to_json(session, f"{api}/get/fetchVideoDetailsById?course_id={selected_batch_id}&folder_wise_course={folder_wise_course}&ytflag={ytFlag}&video_id={video_id}", headers)
        if not res or res.get('status') != 200:
            res = await fetch_appx_html_to_json(session, f"{api}/get/fetchVideoDetailsById?course_id={selected_batch_id}&folder_wise_course={folder_wise_course}&ytflag={ytFlag}&video_id={video_id}", headers_noauth)

        output = []
        if res:
            data = res.get('data', [])

            if data:
                Title = data.get("Title", f"Video {video_id}")
                
                # 🚨 FIXED: Try direct video URL from response first
                direct_video_url = (
                    data.get('video_url') or data.get('videoUrl') or data.get('hls_url')
                    or data.get('hlsUrl') or data.get('stream_url') or data.get('streamUrl')
                    or data.get('media_url') or data.get('mediaUrl') or data.get('mpd_url')
                    or data.get('mpdUrl') or data.get('download_url') or data.get('downloadUrl')
                    or data.get('url') or data.get('file_url') or data.get('fileUrl')
                    or data.get('source_url') or data.get('sourceUrl') or data.get('path')
                    or data.get('link') or data.get('src') or data.get('video_link') or data.get('videoLink')
                    or ""
                )
                
                if direct_video_url:
                    output.append(f"{Title}:{direct_video_url}\n")
                else:
                    # Try DRM links - without auth fallback
                    res_drm = await fetch_appx_html_to_json(session, f"{api}/get/get_mpd_drm_links?videoid={video_id}&folder_wise_course={folder_wise_course}", headers)
                    if not res_drm or res_drm.get('status') != 200:
                        res_drm = await fetch_appx_html_to_json(session, f"{api}/get/get_mpd_drm_links?videoid={video_id}&folder_wise_course={folder_wise_course}", headers_noauth)
                    
                    if res_drm:
                        drm_data = res_drm.get('data', [])
                        if drm_data and isinstance(drm_data, list) and len(drm_data) > 0:
                            path = appx_decrypt(drm_data[0].get("path", "")) if drm_data[0].get("path") else None
                            if path:
                                output.append(f"{Title}:{path}\n")
                        
                        # Try other DRM fields
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
                                        except:
                                            if val.startswith('http') or val.startswith('//'):
                                                if val.startswith('//'):
                                                    val = f"https:{val}"
                                                output.append(f"{Title}:{val}\n")
                                                break
                
                # PDF extraction (same as before)
                pdf_link = appx_decrypt(data.get("pdf_link", "")) if data.get("pdf_link", "") and appx_decrypt(data.get("pdf_link", "")).endswith(".pdf") else None
                is_pdf_encrypted = data.get("is_pdf_encrypted", 0)
                if pdf_link:
                    if is_pdf_encrypted == 1 or is_pdf_encrypted == "1":
                        key = appx_decrypt(data.get("pdf_encryption_key", "")) if data.get("pdf_encryption_key") else None
                        if key:
                            output.append(f"{Title}:{pdf_link}*{key}\n")
                        else:
                            output.append(f"{Title}:{pdf_link}\n")
                    else:
                        output.append(f"{Title}:{pdf_link}\n")

                # Second PDF link
                pdf_link2 = appx_decrypt(data.get("pdf_link2", "")) if data.get("pdf_link2", "") and appx_decrypt(data.get("pdf_link2", "")).endswith(".pdf") else None
                    
                is_pdf2_encrypted = data.get("is_pdf2_encrypted", 0)
                if pdf_link2:
                    if is_pdf2_encrypted == 1 or is_pdf2_encrypted == "1":
                        key = appx_decrypt(data.get("pdf2_encryption_key", "")) if data.get("pdf2_encryption_key") else None
                        if key:
                            output.append(f"{Title}:{pdf_link2}*{key}\n")
                        else:
                            output.append(f"{Title}:{pdf_link2}\n")
                    else:
                        output.append(f"{Title}:{pdf_link2}\n")

            else:
                output.append(f"Did Not Found Course_id : {selected_batch_id} Video_id : {video_id}\n")
        else:
            output.append(f"Did Not Found Course_id : {selected_batch_id} Video_id : {video_id}\n")

        return output

    except Exception as e:
        return [
            f"User ID: {user_id} - An error occurred while fetching details for Course_id : {selected_batch_id}, video ID {video_id}: {str(e)}\n"]



async def fetch_appx_folder_contents_v2(session, api, selected_batch_id, folder_id, headers, folder_wise_course, user_id):
    logging.info(f"User ID: {user_id} - Fetching folder contents for folder ID: {folder_id}")
    try:
        res = await fetch_appx_html_to_json(session, f"{api}/get/folder_contentsv2?course_id={selected_batch_id}&parent_id={folder_id}", headers)
        tasks = []
        output = []
        if "data" in res:
            data = res["data"]
            for item in data:
                Title = item.get("Title")
                video_id = item.get("id")
                ytFlag = item.get("ytFlag")

                if item.get("material_type") == "VIDEO":
                    tasks.append(
                        fetch_appx_video_id_details_v2(session, api, selected_batch_id, video_id, ytFlag, headers, folder_wise_course, user_id))

                elif item.get("material_type") == "FOLDER":
                    tasks.append(
                        fetch_appx_folder_contents_v2(session, api, selected_batch_id, item.get("id"), headers, folder_wise_course, user_id))

        if tasks:
            results = await asyncio.gather(*tasks)
            for res in results:
                if isinstance(res, list):
                    output.extend(res)
                else:
                    output.append(res)
        return output
    except Exception as e:
        return [
            f"User ID: {user_id} - Error fetching folder contents for folder - Course_id : {selected_batch_id}, Folder_id : {folder_id}. Error: {e}\n"]




async def fetch_appx_video_id_details_v3(session, api, selected_batch_id, video_id, ytFlag, headers, user_id):
    logging.info(f"User ID: {user_id} - Fetching video details V3 for video ID: {video_id}")
    try:
        # 🚨 FIXED: Try with original headers first, then without auth if that fails
        # Create two header versions: with auth and without
        headers_noauth = {k: v for k, v in headers.items() if k.lower() not in ('authorization', 'user-id')}
        
        # Try with auth headers first (if present)
        res = await fetch_appx_html_to_json(session, f"{api}/get/fetchVideoDetailsById?course_id={selected_batch_id}&folder_wise_course=0&ytflag={ytFlag}&video_id={video_id}", headers)
        
        # If failed, try without auth
        if not res or res.get('status') != 200:
            logging.info(f"User ID: {user_id} - Auth failed, trying without auth for video ID: {video_id}")
            res = await fetch_appx_html_to_json(session, f"{api}/get/fetchVideoDetailsById?course_id={selected_batch_id}&folder_wise_course=0&ytflag={ytFlag}&video_id={video_id}", headers_noauth)

        output = []
        if res:
            data = res.get('data', [])
            
            # 🚨 FIXED: Check if data already has video URL directly (without needing drm_links)
            if data:
                Title = data.get("Title", f"Video {video_id}")
                
                # Try to get video URL directly from the response data
                direct_video_url = (
                    data.get('video_url')
                    or data.get('videoUrl')
                    or data.get('hls_url')
                    or data.get('hlsUrl')
                    or data.get('stream_url')
                    or data.get('streamUrl')
                    or data.get('media_url')
                    or data.get('mediaUrl')
                    or data.get('mpd_url')
                    or data.get('mpdUrl')
                    or data.get('download_url')
                    or data.get('downloadUrl')
                    or data.get('url')
                    or data.get('file_url')
                    or data.get('fileUrl')
                    or data.get('source_url')
                    or data.get('sourceUrl')
                    or data.get('path')
                    or data.get('link')
                    or data.get('src')
                    or data.get('video_link')
                    or data.get('videoLink')
                    or ""
                )
                
                if direct_video_url:
                    output.append(f"{Title}:{direct_video_url}\n")
                    logging.info(f"User ID: {user_id} - Direct video URL found in fetchVideoDetailsById for: {Title}")
                else:
                    # Try the DRM links endpoint
                    # Try with auth first, then without
                    res_drm = await fetch_appx_html_to_json(session, f"{api}/get/get_mpd_drm_links?folder_wise_course=0&videoid={video_id}", headers)
                    if not res_drm or res_drm.get('status') != 200:
                        res_drm = await fetch_appx_html_to_json(session, f"{api}/get/get_mpd_drm_links?folder_wise_course=0&videoid={video_id}", headers_noauth)
                    
                    if res_drm:
                        drm_data = res_drm.get('data', [])
                        if drm_data and isinstance(drm_data, list) and len(drm_data) > 0:
                            path = appx_decrypt(drm_data[0].get("path", "")) if drm_data[0].get("path") else None
                            if path:
                                output.append(f"{Title}:{path}\n")
                        else:
                            drm_data = []
                    else:
                        drm_data = []
                    
                    # 🚨 FIXED: Also try other fields in DRM response
                    if not output and drm_data and isinstance(drm_data, list):
                        for item in drm_data:
                            for field in ['path', 'url', 'videoUrl', 'hlsUrl', 'mpdUrl', 'streamUrl', 'mediaUrl', 'downloadUrl', 'fileUrl', 'link', 'src']:
                                val = item.get(field)
                                if val:
                                    try:
                                        decrypted = appx_decrypt(val) if val else None
                                        if decrypted and (decrypted.startswith('http') or decrypted.startswith('//') or decrypted.startswith('/')):
                                            if not decrypted.startswith('http'):
                                                decrypted = f"https:{decrypted}" if decrypted.startswith('//') else f"{api.rstrip('/')}/{decrypted.lstrip('/')}"
                                            output.append(f"{Title}:{decrypted}\n")
                                            break
                                    except:
                                        if val.startswith('http') or val.startswith('//'):
                                            if val.startswith('//'):
                                                val = f"https:{val}"
                                            output.append(f"{Title}:{val}\n")
                                            break
                
                # Also extract PDF links from this response (backup)
                pdf_link = appx_decrypt(data.get("pdf_link", "")) if data.get("pdf_link", "") and appx_decrypt(data.get("pdf_link", "")).endswith(".pdf") else None
                is_pdf_encrypted = data.get("is_pdf_encrypted", 0)
                if pdf_link:
                    if is_pdf_encrypted == 1 or is_pdf_encrypted == "1":
                        key = appx_decrypt(data.get("pdf_encryption_key", "")) if data.get("pdf_encryption_key") else None
                        if key:
                            output.append(f"{Title}:{pdf_link}*{key}\n")
                        else:
                            output.append(f"{Title}:{pdf_link}\n")
                    else:
                        output.append(f"{Title}:{pdf_link}\n")

                is_pdf_encrypted = data.get("is_pdf_encrypted", 0)
                if pdf_link:
                    if is_pdf_encrypted == 1 or is_pdf_encrypted == "1":
                        key = appx_decrypt(data.get("pdf_encryption_key", "")) if data.get("pdf_encryption_key") else None
                        if key:
                            output.append(f"{Title}:{pdf_link}*{key}\n")
                        else:
                            output.append(f"{Title}:{pdf_link}\n")
                    else:
                        output.append(f"{Title}:{pdf_link}\n")

                # Second PDF link
                pdf_link2 = appx_decrypt(data.get("pdf_link2", "")) if data.get("pdf_link2", "") and appx_decrypt(data.get("pdf_link2", "")).endswith(".pdf") else None

                is_pdf2_encrypted = data.get("is_pdf2_encrypted", 0)
                if pdf_link2:
                    if is_pdf2_encrypted == 1 or is_pdf2_encrypted == "1":
                        key = appx_decrypt(data.get("pdf2_encryption_key", "")) if data.get("pdf2_encryption_key") else None
                        if key:
                            output.append(f"{Title}:{pdf_link2}*{key}\n")
                        else:
                            output.append(f"{Title}:{pdf_link2}\n")
                    else:
                        output.append(f"{Title}:{pdf_link2}\n")
            else:
                output.append(f"Did Not Found Course_id : {selected_batch_id} Video_id : {video_id}\n")
        else:
            output.append(f"Did Not Found Course_id : {selected_batch_id} Video_id : {video_id}\n")

        return output

    except Exception as e:
        return [
            f"User ID: {user_id} - An error occurred while fetching details for Course_id : {selected_batch_id}, video ID {video_id}: {str(e)}\n"]



def find_appx_matching_apis(search_api, appxapis_file="appxapis.json"):
    matched_apis = []

    try:
        with open(appxapis_file, 'r') as f:
            api_data = json.load(f)
    except FileNotFoundError:
        logging.error(f"Error: Could not find the file: {appxapis_file}")
        return matched_apis
    except json.JSONDecodeError:
        logging.error(f"Error: Invalid JSON format in the file: {appxapis_file}")
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



async def process_folder_wise_course_0(session, api, selected_batch_id, headers, user_id):
    logging.info(f"User ID: {user_id} - Processing folder-wise course 0")
    res = await fetch_appx_html_to_json(session, f"{api}/get/allsubjectfrmlivecourseclass?courseid={selected_batch_id}&start=-1", headers)
    all_outputs = []
    tasks = []
    if res and "data" in res:
        subjects = res["data"]
        for subject in subjects:
            subjectid = subject.get("subjectid")

            res2 = await fetch_appx_html_to_json(session, f"{api}/get/alltopicfrmlivecourseclass?courseid={selected_batch_id}&subjectid={subjectid}&start=-1", headers)
            if res2 and "data" in res2:
                topics = res2["data"]
                for topic in topics:
                    topicid = topic.get("topicid")

                    res3 = await fetch_appx_html_to_json(session, f"{api}/get/livecourseclassbycoursesubtopconceptapiv3?topicid={topicid}&start=-1&courseid={selected_batch_id}&subjectid={subjectid}", headers)
                    if res3 and "data" in res3:
                        data = res3["data"]
                        for item in data:
                            Title = item.get("Title")
                            video_id = item.get("id")
                            ytFlag = item.get("ytFlag")

                            if item.get("material_type") == "PDF" or item.get("material_type") == "TEST":
                                Title = item.get("Title")
                                
                                pdf_link = appx_decrypt(item.get("pdf_link", "")) if item.get("pdf_link", "") and appx_decrypt(item.get("pdf_link", "")).endswith(".pdf") else None
                                                              
                                is_pdf_encrypted = item.get("is_pdf_encrypted")

                                if pdf_link:
                                    if is_pdf_encrypted == 1 or is_pdf_encrypted == "1":
                                        key = appx_decrypt(item.get("pdf_encryption_key"))
                                        if key:
                                            all_outputs.append(f"{Title}:{pdf_link}*{key}\n")
                                        else:
                                            all_outputs.append(f"{Title}:{pdf_link}\n")
                                    else:
                                        all_outputs.append(f"{Title}:{pdf_link}\n")
                                        
                                pdf_link2 = appx_decrypt(item.get("pdf_link2", "")) if item.get("pdf_link2", "") and appx_decrypt(item.get("pdf_link2", "")).endswith(".pdf") else None
                                    
                                is_pdf2_encrypted = item.get("is_pdf2_encrypted")

                                if pdf_link2:
                                    if is_pdf2_encrypted == 1 or is_pdf2_encrypted == "1":
                                        key = appx_decrypt(item.get("pdf2_encryption_key"))
                                        if key:
                                            all_outputs.append(f"{Title}:{pdf_link2}*{key}\n")
                                        else:
                                            all_outputs.append(f"{Title}:{pdf_link2}\n")
                                    else:
                                        all_outputs.append(f"{Title}:{pdf_link2}\n")

                            elif item.get("material_type") == "IMAGE":
                                thumbnail = item.get("thumbnail")
                                if thumbnail:
                                    all_outputs.append(f"{Title}:{thumbnail}\n")
                                    
                            elif item.get("material_type") == "VIDEO":
                                # 🚨 FIXED: First try to get video URL directly from item data
                                # Many Appx platforms include video URL in the items list response
                                direct_video_url = (
                                    item.get('video_url')
                                    or item.get('videoUrl')
                                    or item.get('hls_url')
                                    or item.get('hlsUrl')
                                    or item.get('stream_url')
                                    or item.get('streamUrl')
                                    or item.get('media_url')
                                    or item.get('mediaUrl')
                                    or item.get('mpd_url')
                                    or item.get('mpdUrl')
                                    or item.get('download_url')
                                    or item.get('downloadUrl')
                                    or item.get('url')
                                    or item.get('file_url')
                                    or item.get('fileUrl')
                                    or item.get('video_link')
                                    or item.get('videoLink')
                                    or item.get('source_url')
                                    or item.get('sourceUrl')
                                    or item.get('path')
                                    or item.get('link')
                                    or item.get('src')
                                )
                                
                                # Also check if encrypted fields contain video URLs
                                if not direct_video_url:
                                    direct_video_url = (
                                        appx_decrypt(item.get("pdf_link", "")) if item.get("pdf_link") and not appx_decrypt(item.get("pdf_link", "")).endswith(".pdf") else None
                                        or appx_decrypt(item.get("pdf_link2", "")) if item.get("pdf_link2") and not appx_decrypt(item.get("pdf_link2", "")).endswith(".pdf") else None
                                        or appx_decrypt(item.get("file_link", "")) if item.get("file_link") else None
                                    )
                                
                                # If we found an encrypted path, try to build URL from it
                                if direct_video_url:
                                    if direct_video_url.startswith("http"):
                                        all_outputs.append(f"{Title}:{direct_video_url}\n")
                                        logging.info(f"User ID: {user_id} - Direct video URL found in items list for: {Title}")
                                    elif direct_video_url and not direct_video_url.startswith("http"):
                                        # Might be a relative path - try constructing full URL
                                        if '/' in direct_video_url:
                                            # Try to build from api base
                                            api_base = api.rstrip('/')
                                            constructed = f"{api_base}/{direct_video_url.lstrip('/')}"
                                            all_outputs.append(f"{Title}:{constructed}\n")
                                            logging.info(f"User ID: {user_id} - Constructed video URL from relative path: {constructed}")
                                else:
                                    # No direct URL found, fall back to API calls
                                    if selected_batch_id is not None and video_id is not None and ytFlag is not None:
                                        tasks.append(
                                            fetch_appx_video_id_details_v3(session, api, selected_batch_id, video_id, ytFlag, headers, user_id))
                                    else:
                                        logging.warning(
                                            f"User ID: {user_id} - Skipping video due to None value: course_id={selected_batch_id}, video_id={video_id}, ytflag={ytFlag}")
                    else:
                        logging.warning(f"User ID: {user_id} - No data found in livecourseclassbycoursesubtopconceptapiv3 API response")
            else:
                logging.warning(f"User ID: {user_id} - No data found in alltopicfrmlivecourseclass API response")
    else:
        logging.warning(f"User ID: {user_id} - No data found in allsubjectfrmlivecourseclass API response")

    if tasks:
        results = await asyncio.gather(*tasks)
        for res in results:
            all_outputs.extend(res)

    return all_outputs



async def process_folder_wise_course_1(session, api, selected_batch_id, headers, user_id):
    logging.info(f"User ID: {user_id} - Processing folder-wise course 1")
    res = await fetch_appx_html_to_json(session, f"{api}/get/folder_contentsv2?course_id={selected_batch_id}&parent_id=-1", headers)
    all_outputs = []
    tasks = []
    if res and "data" in res:
        data = res["data"]
        for item in data:
            Title = item.get("Title")
            video_id = item.get("id")
            ytFlag = item.get("ytFlag")
            
            if item.get("material_type") == "PDF" or item.get("material_type") == "TEST":
                Title = item.get("Title")
                
                pdf_link = appx_decrypt(item.get("pdf_link", "")) if item.get("pdf_link", "") and appx_decrypt(item.get("pdf_link", "")).endswith(".pdf") else None
                    
                is_pdf_encrypted = item.get("is_pdf_encrypted")

                if pdf_link:
                    if is_pdf_encrypted == 1 or is_pdf_encrypted == "1":
                        key = appx_decrypt(item.get("pdf_encryption_key"))
                        if key:
                            all_outputs.append(f"{Title}:{pdf_link}*{key}\n")
                        else:
                            all_outputs.append(f"{Title}:{pdf_link}\n")
                    else:
                        all_outputs.append(f"{Title}:{pdf_link}\n")
                        
                pdf_link2 = appx_decrypt(item.get("pdf_link2", "")) if item.get("pdf_link2", "") and appx_decrypt(item.get("pdf_link2", "")).endswith(".pdf") else None
                    
                is_pdf2_encrypted = item.get("is_pdf2_encrypted")

                if pdf_link2:
                    if is_pdf2_encrypted == 1 or is_pdf2_encrypted == "1":
                        key = appx_decrypt(item.get("pdf2_encryption_key"))
                        if key:
                            all_outputs.append(f"{Title}:{pdf_link2}*{key}\n")
                        else:
                            all_outputs.append(f"{Title}:{pdf_link2}\n")
                    else:
                        all_outputs.append(f"{Title}:{pdf_link2}\n")

            elif item.get("material_type") == "IMAGE":
                thumbnail = item.get("thumbnail")
                if thumbnail:
                   all_outputs.append(f"{Title}:{thumbnail}\n")
                   
            elif item.get("material_type") == "VIDEO":
                # 🚨 FIXED: First try direct video URL from item data
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
                        logging.info(f"User ID: {user_id} - Direct video URL in items list for: {Title}")
                    elif '/' in direct_video_url:
                        constructed = f"{api.rstrip('/')}/{direct_video_url.lstrip('/')}"
                        all_outputs.append(f"{Title}:{constructed}\n")
                        logging.info(f"User ID: {user_id} - Constructed video URL: {constructed}")
                else:
                    tasks.append(
                        fetch_appx_video_id_details_v2(session, api, selected_batch_id, video_id, ytFlag, headers, 1, user_id))

            elif item.get("material_type") == "FOLDER":
                tasks.append(fetch_appx_folder_contents_v2(session, api, selected_batch_id, item.get("id"), headers, 1, user_id))

    if tasks:
        results = await asyncio.gather(*tasks)
        for res in results:
            all_outputs.extend(res)

    return all_outputs



@bot.on_callback_query(filters.regex("^appxwp$"))
async def appxwp_callback(bot, callback_query):
    user_id = callback_query.from_user.id
    await callback_query.answer()

    auth_user = auth_users[0]
    user = await bot.get_users(auth_user)
    owner_username = "@durov" 

    if user_id not in auth_users:
        await bot.send_message(callback_query.message.chat.id, f"**You Are Not Subscribed To This Bot\nContact - {owner_username}**")
        return
        
    THREADPOOL.submit(asyncio.run, process_appxwp(bot, callback_query.message, user_id))




async def process_appxwp(bot: Client, m: Message, user_id: int):

    loop = asyncio.get_event_loop()
    CONNECTOR = aiohttp.TCPConnector(limit=100, loop=loop)

    async with aiohttp.ClientSession(connector=CONNECTOR, loop=loop) as session:
        try:
            editable = await m.reply_text("**Enter App Name Or Api**")

            try:
                input1 = await bot.listen(chat_id=m.chat.id, filters=filters.user(user_id), timeout=120)
                api = input1.text
                await input1.delete(True)
            except:
                await editable.edit("**Timeout! You took too long to respond**")
                return

            if not (api.startswith("http://") or api.startswith("https://")):

                api = api
                search_api = [term.strip() for term in api.split()]

                matches = find_appx_matching_apis(search_api)

                if matches:
                    text = ''
                    for cnt, item in enumerate(matches):
                        name = item['name']
                        api = item["api"]
                        text += f'{cnt + 1}. ```\n{name}:{api}```\n'
                        
                    await editable.edit(f"**Send index number of the Batch to download.\n\n{text}**")

                    try:
                        input2 = await bot.listen(chat_id=m.chat.id, filters=filters.user(user_id), timeout=120)
                        raw_text2 = input2.text
                        await input2.delete(True)
                    except:
                        await editable.edit("**Timeout! You took too long to respond**")
                        return
                
                    if input2.text.isdigit() and 1 <= int(input2.text) <= len(matches):
                        selected_api_index = int(input2.text.strip())
                        item = matches[selected_api_index - 1]
                        api = item['api']
                        selected_app_name = item['name']

                    else:
                        await editable.edit("**Error : Wrong Index Number**")
                        return
                else:
                    await editable.edit("**No matches found. Enter Correct App Starting Word**")
                    return
            else:
                api = api = "https://" + api.replace("https://", "").replace("http://", "").rstrip("/")
                selected_app_name = api

            # 🚨 FIXED: Removed bogus placeholder token "eyJ0eX...hdAg"
            # Video extraction now tries WITHOUT auth first (many Appx endpoints work without it)
            # User can optionally provide a token by entering it at the app name prompt
            token = None
            userid = None
            
            # Check if user input looks like a JWT token instead of an app name
            user_input = api
            if user_input and user_input.count('.') == 2 and len(user_input) > 100:
                # User provided a JWT token directly
                token = user_input
                await editable.edit("**Token received! Now enter App Name or Api**")
                try:
                    input1b = await bot.listen(chat_id=m.chat.id, filters=filters.user(user_id), timeout=120)
                    api = input1b.text
                    await input1b.delete(True)
                except:
                    await editable.edit("**Timeout! You took too long to respond**")
                    return
                if not (api.startswith("http://") or api.startswith("https://")):
                    search_api = [term.strip() for term in api.split()]
                    matches = find_appx_matching_apis(search_api)
                    if matches:
                        text = ''
                        for cnt, item in enumerate(matches):
                            name = item['name']
                            api_url = item["api"]
                            text += f'{cnt + 1}. ```\\n{name}:{api_url}```\\n'
                        await editable.edit(f"**Send index number of the Batch to download.\\n\\n{text}**")
                        try:
                            input2b = await bot.listen(chat_id=m.chat.id, filters=filters.user(user_id), timeout=120)
                            raw_text2b = input2b.text
                            await input2b.delete(True)
                        except:
                            await editable.edit("**Timeout! You took too long to respond**")
                            return
                        if input2b.text.isdigit() and 1 <= int(input2b.text) <= len(matches):
                            selected_api_index = int(input2b.text.strip())
                            item = matches[selected_api_index - 1]
                            api = item['api']
                            selected_app_name = item['name']
                        else:
                            await editable.edit("**Error : Wrong Index Number**")
                            return
                    else:
                        await editable.edit("**No matches found. Enter Correct App Starting Word**")
                        return
                else:
                    api = "https://" + api.replace("https://", "").replace("http://", "").rstrip("/")
                    selected_app_name = api
            
            headers = {
                'User-Agent': "okhttp/4.9.1",
                'Accept-Encoding': "gzip",
                'client-service': "Appx",
                'auth-key': "appxapi",
                'user_app_category': "",
                'language': "en",
                'device_type': "ANDROID"
            }
            # Only add auth if user provided a token
            if token:
                headers['authorization'] = f"Bearer {token}"
                headers['user-id'] = userid or "0"
            
            res1 = await fetch_appx_html_to_json(session, f"{api}/get/courselist", headers)
            res2 = await fetch_appx_html_to_json(session, f"{api}/get/courselistnewv2", headers)

            courses1 = res1.get("data", []) if res1 and res1.get('status') == 200 else []
            total1 = res1.get("total", 0) if res1 and res1.get('status') == 200 else 0

            courses2 = res2.get("data", []) if res2 and res2.get('status') == 200 else []
            total2 = res2.get("total", 0) if res2 and res2.get('status') == 200 else 0
            
            courses = courses1 + courses2
            total = total1 + total2

            if courses:
                if total > 50:
                    text = ''
                    for cnt, course in enumerate(courses):
                        name = course["course_name"]
                        price = course["price"]
                        text += f'{cnt + 1}. {name} 💵₹{price}\n'
                    
                    course_details = f"{user_id}_paid_course_details"
                
                    with open(f"{course_details}.txt", 'w') as f:
                        f.write(text)
                        
                    caption = f"**App Name : ```\n{selected_app_name}```\nBatch Name : ```\nPaid Course Details```**"
                                
                    files = [f"{course_details}.{ext}" for ext in ["txt"]]
                                
                    for file in files:
                        file_ext = os.path.splitext(file)[1][1:]
                        try:
                            with open(file, 'rb') as f:
                                await editable.delete(True)
                                doc = await m.reply_document(document=f, caption=caption, file_name=f"paid course details.{file_ext}")
                                editable = await m.reply_text("**Send index number From the course details txt File to download.**")
                        except FileNotFoundError:
                            logging.error(f"File not found: {file}")
                        except Exception as e:
                            logging.exception(f"Error sending document {file}:")
                        finally:
                            try:
                                os.remove(file)
                                logging.info(f"Removed File After Sending : {file}")
                            except OSError as e:
                                logging.error(f"Error deleting {file}: {e}")
                else:
                    text = ''
                    for cnt, course in enumerate(courses):
                        name = course["course_name"]
                        price = course["price"]
                        text += f'{cnt + 1}. ```\n{name} 💵₹{price}```\n'
                    await editable.edit(f"**Send index number of the course to download.\n\n{text}**")
            else:
                raise Exception("Did not found any course")
                
            try:
                input5 = await bot.listen(chat_id=m.chat.id, filters=filters.user(user_id), timeout=120)
                raw_text5 = input5.text
                await input5.delete(True)
            except:
                await editable.edit("**Timeout! You took too long to respond**")
                return
                
            if input5.text.isdigit() and 1 <= int(input5.text) <= len(courses):
                selected_course_index = int(input5.text.strip())
                course = courses[selected_course_index - 1]
                selected_batch_id = course['id']
                selected_batch_name = course['course_name']
                folder_wise_course = course.get("folder_wise_course", "")
                clean_batch_name = f"{selected_batch_name.replace('/', '-').replace('|', '-')[:min(244, len(selected_batch_name))]}"
                clean_file_name = f"{user_id}_{clean_batch_name}"
                
            else:
                raise Exception("Wrong Index Number")
        
            await editable.edit(f"**Extracting course : {selected_batch_name} ...**")
            
            start_time = time.time()
            
            headers = {}
            # Only add auth headers if user provided a token
            if token:
                headers = {
                    "Client-Service": "Appx",
                    "Auth-Key": "appxapi",
                    "source": "website",
                    "Authorization": token,
                    "User-ID": userid or "0"
                }
            else:
                headers = {
                    "Client-Service": "Appx",
                    "Auth-Key": "appxapi",
                    "source": "website",
                }

            all_outputs = []

            if folder_wise_course == 0:
                logging.info(f"User ID: {user_id} - Processing as non-folder-wise (folder_wise_course = 0)")
                all_outputs = await process_folder_wise_course_0(session, api, selected_batch_id, headers, user_id)

            elif folder_wise_course == 1:
                logging.info(f"User ID: {user_id} - Processing as folder-wise (folder_wise_course = 1)")
                all_outputs = await process_folder_wise_course_1(session, api, selected_batch_id, headers, user_id)

            else:
                logging.info(f"User ID: {user_id} - folder_wise_course is neither 0 nor 1.  Processing with both methods sequentially.")
                # Process as if folder_wise_course is 0
                logging.info(f"User ID: {user_id} - Processing as non-folder-wise (folder_wise_course = 0)")
                outputs_0 = await process_folder_wise_course_0(session, api, selected_batch_id, headers, user_id)
                all_outputs.extend(outputs_0)

                # Process as if folder_wise_course is 1
                logging.info(f"User ID: {user_id} - Processing as folder-wise (folder_wise_course = 1)")
                outputs_1 = await process_folder_wise_course_1(session, api, selected_batch_id, headers, user_id)
                all_outputs.extend(outputs_1)
            
            if all_outputs:
            
                with open(f"{clean_file_name}.txt", 'w') as f:
                    for output_line in all_outputs:
                        f.write(output_line)
                        
                end_time = time.time()
                response_time = end_time - start_time
                minutes = int(response_time // 60)
                seconds = int(response_time % 60)

                if minutes == 0:
                    if seconds < 1:
                        formatted_time = f"{response_time:.2f} seconds"
                    else:
                        formatted_time = f"{seconds} seconds"
                else:
                    formatted_time = f"{minutes} minutes {seconds} seconds"
                                    
                caption = f"**App Name : ```\n{selected_app_name}```\nBatch Name : ```\n{selected_batch_name}``````\nTime Taken : {formatted_time}```**"
                                
                files = [f"{clean_file_name}.{ext}" for ext in ["txt"]]
                for file in files:
                    file_ext = os.path.splitext(file)[1][1:]
                    try:
                        with open(file, 'rb') as f:
                            await editable.delete(True)
                            doc = await m.reply_document(document=f, caption=caption, file_name=f"{clean_batch_name}.{file_ext}")
                    except FileNotFoundError:
                        logging.error(f"File not found: {file}")
                    except Exception as e:
                        logging.exception(f"Error sending document {file}:")
                    finally:
                        try:
                            os.remove(file)
                            logging.info(f"Removed File After Sending : {file}")
                        except OSError as e:
                            logging.error(f"Error deleting {file}: {e}")
            else:
                raise Exception("Didn't Found Any Content In The Course")
                
            
        except Exception as e:
            logging.exception(f"An unexpected error occurred: {e}")
            try:
                await editable.edit(f"**Error : {e}**")
            except Exception as ee:
                logging.error(f"Failed to send error message to user in callback: {ee}")
        finally:
            if session:
                await session.close()
            await CONNECTOR.close()


                                        
bot.run()


