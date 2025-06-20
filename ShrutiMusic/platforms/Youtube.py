import asyncio
import os
import re
import json
from typing import Union, Optional, Dict, Any
from pathlib import Path
import requests
import yt_dlp
import aiohttp
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from youtubesearchpython.__future__ import VideosSearch
from ShrutiMusic.utils.database import is_on_off
from ShrutiMusic.utils.formatters import time_to_seconds
import config
from config import API_URL, API_KEY


class HttpxClient:
    """HTTP client for making requests"""
    
    async def make_request(self, url: str, max_retries: int = 3) -> Optional[Dict[str, Any]]:
        """Make HTTP request with retries"""
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as response:
                        if response.status == 200:
                            return await response.json()
                        else:
                            print(f"Request failed with status {response.status}")
            except Exception as e:
                print(f"Request attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
        return None
    
    async def download_file(self, url: str) -> Dict[str, Any]:
        """Download file from URL"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        # Generate filename from URL or use video ID
                        filename = url.split('/')[-1] or "download"
                        if not filename.endswith(('.mp3', '.m4a', '.webm')):
                            filename += '.mp3'
                        
                        file_path = os.path.join("downloads", filename)
                        os.makedirs("downloads", exist_ok=True)
                        
                        with open(file_path, 'wb') as f:
                            async for chunk in response.content.iter_chunked(8192):
                                f.write(chunk)
                        
                        return {"success": True, "file_path": file_path}
                    else:
                        return {"success": False, "error": f"HTTP {response.status}"}
        except Exception as e:
            return {"success": False, "error": str(e)}


def cookie_txt_file():
    """Get random cookie file"""
    cookie_dir = f"{os.getcwd()}/cookies"
    if not os.path.exists(cookie_dir):
        return None
    
    cookies_files = [f for f in os.listdir(cookie_dir) if f.endswith(".txt")]
    if not cookies_files:
        return None
    
    import random
    cookie_file = os.path.join(cookie_dir, random.choice(cookies_files))
    return cookie_file


async def download_with_api(video_id: str, is_video: bool = False) -> Union[None, str]:
    """
    Download using AshokShau's API method
    """
    if not API_URL or not API_KEY:
        return None
    
    httpx = HttpxClient()
    api_response = await httpx.make_request(f"{API_URL}/yt?id={video_id}&video={is_video}")
    
    if not api_response:
        print("API request failed")
        return None
    
    dl_url = api_response.get("results")
    if not dl_url:
        print("No download URL in API response")
        return None
    
    # Check if it's a Telegram link
    if re.fullmatch(r"https:\/\/t\.me\/([a-zA-Z0-9_]{5,})\/(\d+)", dl_url):
        print("Telegram link detected - not supported in this version")
        return None
    
    # Direct download
    download_result = await httpx.download_file(dl_url)
    if download_result.get("success"):
        return download_result["file_path"]
    
    return None


async def download_song(link: str):
    """Enhanced download function with API fallback"""
    video_id = link.split('v=')[-1].split('&')[0]
    
    # Check if file already exists
    download_folder = "downloads"
    os.makedirs(download_folder, exist_ok=True)
    
    for ext in ["mp3", "m4a", "webm"]:
        file_path = f"{download_folder}/{video_id}.{ext}"
        if os.path.exists(file_path):
            return file_path
    
    # Try API method first (AshokShau's method)
    if API_URL and API_KEY:
        api_file = await download_with_api(video_id)
        if api_file:
            return api_file
    
    # Fallback to old API method
    if API_URL and API_KEY:
        song_url = f"{API_URL}/song/{video_id}?api={API_KEY}"
        async with aiohttp.ClientSession() as session:
            while True:
                try:
                    async with session.get(song_url) as response:
                        if response.status != 200:
                            break
                        
                        data = await response.json()
                        status = data.get("status", "").lower()
                        
                        if status == "downloading":
                            await asyncio.sleep(2)
                            continue
                        elif status == "error":
                            print(f"API error: {data.get('error', 'Unknown error')}")
                            break
                        elif status == "done":
                            download_url = data.get("link")
                            if download_url:
                                # Download the file
                                file_format = data.get("format", "mp3")
                                file_name = f"{video_id}.{file_format.lower()}"
                                file_path = os.path.join(download_folder, file_name)
                                
                                async with session.get(download_url) as file_response:
                                    with open(file_path, 'wb') as f:
                                        async for chunk in file_response.content.iter_chunked(8192):
                                            f.write(chunk)
                                return file_path
                            break
                        else:
                            break
                except Exception as e:
                    print(f"Error with fallback API: {e}")
                    break
    
    # Final fallback to yt-dlp
    return await download_with_ytdlp(video_id)


async def download_with_ytdlp(video_id: str, video: bool = False) -> Optional[str]:
    """Download using yt-dlp as final fallback"""
    try:
        cookie_file = cookie_txt_file()
        output_template = f"downloads/{video_id}.%(ext)s"
        
        if video:
            format_selector = "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4][height<=1080]"
        else:
            format_selector = "bestaudio[ext=m4a]/bestaudio[ext=mp4]/bestaudio[ext=webm]/bestaudio/best"
        
        ytdlp_params = [
            "yt-dlp",
            "--no-warnings",
            "--quiet",
            "--geo-bypass",
            "--retries", "2",
            "--continue",
            "--no-part",
            "-o", output_template,
            "-f", format_selector,
        ]
        
        if cookie_file:
            ytdlp_params += ["--cookies", cookie_file]
        
        if video:
            ytdlp_params += ["--merge-output-format", "mp4"]
        
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        ytdlp_params.append(video_url)
        
        proc = await asyncio.create_subprocess_exec(
            *ytdlp_params,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        
        if proc.returncode == 0:
            # Find the downloaded file
            for ext in ["mp3", "m4a", "webm", "mp4"]:
                file_path = f"downloads/{video_id}.{ext}"
                if os.path.exists(file_path):
                    return file_path
        else:
            print(f"yt-dlp failed: {stderr.decode()}")
    
    except Exception as e:
        print(f"yt-dlp download failed: {e}")
    
    return None


async def check_file_size(link):
    """Check file size before download"""
    async def get_format_info(link):
        cookie_file = cookie_txt_file()
        cmd = ["yt-dlp", "-J", link]
        if cookie_file:
            cmd = ["yt-dlp", "--cookies", cookie_file, "-J", link]
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            print(f'Error:\n{stderr.decode()}')
            return None
        return json.loads(stdout.decode())

    def parse_size(formats):
        total_size = 0
        for format in formats:
            if 'filesize' in format and format['filesize']:
                total_size += format['filesize']
        return total_size

    info = await get_format_info(link)
    if info is None:
        return None
    
    formats = info.get('formats', [])
    if not formats:
        return None
    
    total_size = parse_size(formats)
    return total_size


async def shell_cmd(cmd):
    """Execute shell command"""
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, errorz = await proc.communicate()
    if errorz:
        if "unavailable videos are hidden" in (errorz.decode("utf-8")).lower():
            return out.decode("utf-8")
        else:
            return errorz.decode("utf-8")
    return out.decode("utf-8")


class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.status = "https://www.youtube.com/oembed?url="
        self.listbase = "https://youtube.com/playlist?list="
        self.reg = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

    async def exists(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if re.search(self.regex, link):
            return True
        else:
            return False

    async def url(self, message_1: Message) -> Union[str, None]:
        messages = [message_1]
        if message_1.reply_to_message:
            messages.append(message_1.reply_to_message)
        text = ""
        offset = None
        length = None
        for message in messages:
            if offset:
                break
            if message.entities:
                for entity in message.entities:
                    if entity.type == MessageEntityType.URL:
                        text = message.text or message.caption
                        offset, length = entity.offset, entity.length
                        break
            elif message.caption_entities:
                for entity in message.caption_entities:
                    if entity.type == MessageEntityType.TEXT_LINK:
                        return entity.url
        if offset in (None,):
            return None
        return text[offset : offset + length]

    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]:
            title = result["title"]
            duration_min = result["duration"]
            thumbnail = result["thumbnails"][0]["url"].split("?")[0]
            vidid = result["id"]
            if str(duration_min) == "None":
                duration_sec = 0
            else:
                duration_sec = int(time_to_seconds(duration_min))
        return title, duration_min, duration_sec, thumbnail, vidid

    async def title(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]:
            title = result["title"]
        return title

    async def duration(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]:
            duration = result["duration"]
        return duration

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]:
            thumbnail = result["thumbnails"][0]["url"].split("?")[0]
        return thumbnail

    async def video(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        
        cookie_file = cookie_txt_file()
        cmd = ["yt-dlp", "-g", "-f", "best[height<=?720][width<=?1280]", link]
        if cookie_file:
            cmd = ["yt-dlp", "--cookies", cookie_file, "-g", "-f", "best[height<=?720][width<=?1280]", link]
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if stdout:
            return 1, stdout.decode().split("\n")[0]
        else:
            return 0, stderr.decode()

    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        if videoid:
            link = self.listbase + link
        if "&" in link:
            link = link.split("&")[0]
        
        cookie_file = cookie_txt_file()
        cmd = f"yt-dlp -i --get-id --flat-playlist --playlist-end {limit} --skip-download {link}"
        if cookie_file:
            cmd = f"yt-dlp -i --get-id --flat-playlist --cookies {cookie_file} --playlist-end {limit} --skip-download {link}"
        
        playlist = await shell_cmd(cmd)
        try:
            result = playlist.split("\n")
            for key in result:
                if key == "":
                    result.remove(key)
        except:
            result = []
        return result

    async def track(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]:
            title = result["title"]
            duration_min = result["duration"]
            vidid = result["id"]
            yturl = result["link"]
            thumbnail = result["thumbnails"][0]["url"].split("?")[0]
        track_details = {
            "title": title,
            "link": yturl,
            "vidid": vidid,
            "duration_min": duration_min,
            "thumb": thumbnail,
        }
        return track_details, vidid

    async def formats(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        
        cookie_file = cookie_txt_file()
        ytdl_opts = {"quiet": True}
        if cookie_file:
            ytdl_opts["cookiefile"] = cookie_file
        
        ydl = yt_dlp.YoutubeDL(ytdl_opts)
        with ydl:
            formats_available = []
            r = ydl.extract_info(link, download=False)
            for format in r["formats"]:
                try:
                    str(format["format"])
                except:
                    continue
                if not "dash" in str(format["format"]).lower():
                    try:
                        format["format"]
                        format["filesize"]
                        format["format_id"]
                        format["ext"]
                        format["format_note"]
                    except:
                        continue
                    formats_available.append(
                        {
                            "format": format["format"],
                            "filesize": format["filesize"],
                            "format_id": format["format_id"],
                            "ext": format["ext"],
                            "format_note": format["format_note"],
                            "yturl": link,
                        }
                    )
        return formats_available, link

    async def slider(
        self,
        link: str,
        query_type: int,
        videoid: Union[bool, str] = None,
    ):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        a = VideosSearch(link, limit=10)
        result = (await a.next()).get("result")
        title = result[query_type]["title"]
        duration_min = result[query_type]["duration"]
        vidid = result[query_type]["id"]
        thumbnail = result[query_type]["thumbnails"][0]["url"].split("?")[0]
        return title, duration_min, thumbnail, vidid

    async def download(
        self,
        link: str,
        mystic,
        video: Union[bool, str] = None,
        videoid: Union[bool, str] = None,
        songaudio: Union[bool, str] = None,
        songvideo: Union[bool, str] = None,
        format_id: Union[bool, str] = None,
        title: Union[bool, str] = None,
    ) -> str:
        if videoid:
            link = self.base + link
        
        video_id = link.split('v=')[-1].split('&')[0]
        loop = asyncio.get_running_loop()
        
        def audio_dl():
            cookie_file = cookie_txt_file()
            ydl_optssx = {
                "format": "bestaudio/best",
                "outtmpl": "downloads/%(id)s.%(ext)s",
                "geo_bypass": True,
                "nocheckcertificate": True,
                "quiet": True,
                "no_warnings": True,
            }
            if cookie_file:
                ydl_optssx["cookiefile"] = cookie_file
            
            x = yt_dlp.YoutubeDL(ydl_optssx)
            info = x.extract_info(link, False)
            xyz = os.path.join("downloads", f"{info['id']}.{info['ext']}")
            if os.path.exists(xyz):
                return xyz
            x.download([link])
            return xyz

        def video_dl():
            cookie_file = cookie_txt_file()
            ydl_optssx = {
                "format": "(bestvideo[height<=?720][width<=?1280][ext=mp4])+(bestaudio[ext=m4a])",
                "outtmpl": "downloads/%(id)s.%(ext)s",
                "geo_bypass": True,
                "nocheckcertificate": True,
                "quiet": True,
                "no_warnings": True,
            }
            if cookie_file:
                ydl_optssx["cookiefile"] = cookie_file
            
            x = yt_dlp.YoutubeDL(ydl_optssx)
            info = x.extract_info(link, False)
            xyz = os.path.join("downloads", f"{info['id']}.{info['ext']}")
            if os.path.exists(xyz):
                return xyz
            x.download([link])
            return xyz

        # Enhanced download logic with API integration
        if songvideo or songaudio:
            # Use enhanced download_song function
            downloaded_file = await download_song(link)
            if downloaded_file:
                return downloaded_file, True
            # Fallback to old method
            fpath = f"downloads/{video_id}.mp3"
            return fpath, True
            
        elif video:
            if await is_on_off(1):
                # Try API download first
                downloaded_file = await download_song(link)
                if downloaded_file:
                    return downloaded_file, True
                # Fallback to yt-dlp
                downloaded_file = await loop.run_in_executor(None, video_dl)
                return downloaded_file, True
            else:
                # Get direct stream URL
                cookie_file = cookie_txt_file()
                cmd = ["yt-dlp", "-g", "-f", "best[height<=?720][width<=?1280]", link]
                if cookie_file:
                    cmd = ["yt-dlp", "--cookies", cookie_file, "-g", "-f", "best[height<=?720][width<=?1280]", link]
                
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                if stdout:
                    downloaded_file = stdout.decode().split("\n")[0]
                    return downloaded_file, False
                else:
                    # Check file size and download if acceptable
                    file_size = await check_file_size(link)
                    if file_size:
                        total_size_mb = file_size / (1024 * 1024)
                        if total_size_mb > 250:
                            print(f"File size {total_size_mb:.2f} MB exceeds the 250MB limit.")
                            return None
                    
                    # Try API download
                    downloaded_file = await download_song(link)
                    if downloaded_file:
                        return downloaded_file, True
                    
                    # Final fallback
                    downloaded_file = await loop.run_in_executor(None, video_dl)
                    return downloaded_file, True
        else:
            # Audio download with API
            downloaded_file = await download_song(link)
            if downloaded_file:
                return downloaded_file, True
            
            # Fallback to yt-dlp
            downloaded_file = await loop.run_in_executor(None, audio_dl)
            return downloaded_file, True
