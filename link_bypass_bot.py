#!/usr/bin/env python3
"""
Link Bypass Telegram Bot — v3
Handles hdhub4u JS obfuscation by using Playwright (Real Headless Browser)
"""

import os
import re
import socket
import asyncio
import logging
from urllib.parse import urlparse, urljoin, quote
import requests
from playwright.async_api import async_playwright

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)

def check_telegram_api():
    try:
        socket.create_connection(("api.telegram.org", 443), timeout=10)
        return True
    except Exception as e:
        print(f"📡 Network Diagnostic: Cannot reach api.telegram.org: {e}", flush=True)
        return False

BOT_TOKEN = os.getenv("BOT_TOKEN")


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─── SHORTENER DOMAINS ────────────────────────────────────────────────────────
SHORTENER_DOMAINS = {
    "bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly",
    "adf.ly", "adfoc.us", "linkvertise.com", "linkvertise.net",
    "shrinkme.io", "shrink.pe", "shrinkurl.net", "cutt.ly",
    "shorturl.at", "rb.gy", "is.gd", "v.gd", "short.io",
    "clk.sh", "za.gl", "fc.lc", "ouo.io", "ouo.press",
    "exe.io", "gplinks.co", "gplinks.in", "dr.link", "bc.vc",
    "link1s.com", "direct-link.net", "shrtfly.com", "clicksfly.com",
}

DOWNLOAD_EXTENSIONS = {
    ".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".webm",
    ".mp3", ".aac", ".flac", ".wav", ".zip", ".rar", ".7z",
    ".apk", ".exe", ".iso", ".pdf"
}

DIRECT_HOSTS = {
    "drive.google.com", "mega.nz", "mega.co.nz",
    "mediafire.com", "1fichier.com", "pixeldrain.com",
    "gofile.io", "gofile.me", "sendcm.com", "buzzheavier.com",
    "filehaus.com", "krakenfiles.com", "bowfile.com",
    "uploadhaven.com", "clicknupload.co", "rapidgator.net",
    "nitroflare.com", "katfile.com", "ddownload.com",
    "terabox.com", "terabox.app", "1drv.ms", "onedrive.live.com",
    "wetransfer.com", "solidfiles.com", "dood.watch", "streamtape.com",
    "mixdrop.co", "upstream.to", "vtube.to", "voe.sx", "hubdrive.space"
}

def get_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except:
        return ""

def is_direct_link(url: str) -> bool:
    domain = get_domain(url)
    if any(host in domain for host in DIRECT_HOSTS):
        return True
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in DOWNLOAD_EXTENSIONS)

def is_shortener(url: str) -> bool:
    domain = get_domain(url)
    return any(s in domain for s in SHORTENER_DOMAINS)

# ─── SIMPLE BYPASS APIS ───────────────────────────────────────────────────────
def bypass_via_api(url: str) -> str:
    apis = [
        f"https://bypass.bot.nu/bypass?url={quote(url)}",
        f"https://api.bypass.vip/bypass?url={quote(url)}",
    ]
    for api in apis:
        try:
            r = requests.get(api, timeout=15)
            if r.status_code == 200:
                data = r.json()
                res = data.get("destination") or data.get("url") or data.get("bypass")
                if res and isinstance(res, str) and res.startswith("http"):
                    return res
        except:
            continue
    return url

def follow_redirects(url: str) -> str:
    try:
        r = requests.head(url, allow_redirects=True, timeout=10)
        return r.url
    except:
        return url

# ─── PLAYWRIGHT SCRAPER (For hdhub4u JS Decoding) ────────────────────────────
async def scrape_with_playwright(url: str) -> list[dict]:
    results = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        page = await browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        try:
            # Block requests to make it faster
            await page.route("**/*", lambda route: route.abort() 
                             if route.request.resource_type in ["image", "media", "font", "stylesheet"] 
                             else route.continue_())
            
            await page.goto(url, timeout=40000)
            
            # Wait for JS decoders (like b2a) to run
            await page.wait_for_timeout(3000)
            
            # Extract all links with contextual surrounding text for better labeling
            links = await page.evaluate('''() => {
                let items = [];
                let anchors = document.querySelectorAll('a');
                for (let a of anchors) {
                    let label = (a.innerText || a.title || "").trim();
                    let href = a.href || "";
                    
                    if (!href.startsWith('http')) continue;
                    
                    // If the label is extremely generic, try to find context from the parent
                    if (!label || label.toLowerCase() === "download link" || label.toLowerCase() === "download") {
                        let parent = a.parentElement;
                        if (parent && parent.innerText) {
                            let pText = parent.innerText.replace(label, "").trim().split('\\n')[0];
                            if (pText.length > 2 && pText.length < 80) {
                                label = pText + " " + label;
                            } else if (parent.parentElement && parent.parentElement.innerText) {
                                let gText = parent.parentElement.innerText.replace(label, "").trim().split('\\n')[0];
                                if (gText.length > 2 && gText.length < 80) {
                                    label = gText + " " + label;
                                }
                            }
                        }
                    }
                    items.push({text: label, href: href});
                }
                return items;
            }''')
            
            seen = set()
            ignore_domains = {"catimages.org", "imgur.com", "imgbb.com", "postimg.cc", "imgbox.com", "pinterest.com"}
            
            for lnk in links:
                href = lnk.get("href", "").strip()
                if not href.startswith("http"):
                    continue
                
                domain = get_domain(href)
                
                # Filter out pure navigation links
                if domain == get_domain(url) and not is_direct_link(href):
                    continue
                    
                # Filter out image sharing sites
                if domain in ignore_domains:
                    continue
                    
                if href in seen:
                    continue
                seen.add(href)
                
                label = (lnk.get("text") or lnk.get("title") or "Download").strip()
                label = re.sub(r'\s+', ' ', label)
                
                # Check keywords
                valid = False
                if is_direct_link(href) or is_shortener(href):
                    valid = True
                elif any(kw in label.lower() for kw in ["download", "drive", "mega", "480p", "720p", "1080p", "link"]):
                    valid = True
                    
                if valid:
                    results.append({"label": label[:60] or "Link", "url": href})
                    
        except Exception as e:
            logger.error(f"Playwright error: {e}")
        finally:
            await browser.close()
            
    return results

async def deep_bypass_wp_safelink(url: str) -> dict:
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            final_title = "Unknown"
            final_size = "Unknown"
            
            try:
                await page.goto(url, timeout=60000)
                for step in range(20):
                    await page.wait_for_timeout(3500)
                    
                    # Log all open pages for debugging
                    page_urls = [p_idx.url for p_idx in context.pages]
                    logger.info(f"Step {step} - Open Pages: {page_urls}")
                    
                    # Detect hubdrive or hubcloud in any open page
                    hubdrive_page = None
                    # Priority 1: Final server pages or intermediate generation pages
                    for p_idx in reversed(context.pages):
                        if any(k in p_idx.url for k in ['gamerxyt.com', 'hubcdn.fans', 'fsl-buckets', 'hubcloud', 'pixeldrain.dev', 'r2.dev']):
                            hubdrive_page = p_idx
                            break
                    
                    # Priority 2: HubDrive selection page
                    if hubdrive_page is None:
                        for p_idx in reversed(context.pages):
                            if any(k in p_idx.url for k in ['hubdrive', 'drive.google', 'workers.dev']):
                                hubdrive_page = p_idx
                                break
                    
                    if hubdrive_page:
                        logger.info(f"Targeting page: {hubdrive_page.url}")
                        try:
                            await hubdrive_page.wait_for_load_state("domcontentloaded", timeout=5000)
                        except:
                            pass
                            
                        # Assert for type checker
                        assert hubdrive_page is not None
                        # --- HubDrive / HubCloud Extraction ---
                        data = await hubdrive_page.evaluate('''() => {
                            let d = {title: "Unknown", size: "Unknown", links: [], success: false};
                            let h5 = document.querySelector('h5');
                            if(h5) d.title = h5.innerText.trim();
                            
                            let tds = document.querySelectorAll('td');
                            for(let i=0; i<tds.length; i++) {
                                if(tds[i].innerText.includes('Size') && i+1 < tds.length) {
                                    d.size = tds[i+1].innerText.trim();
                                    break;
                                }
                            }

                            // If we are on HubCloud (final server page or generation page)
                            if (window.location.href.includes('gamerxyt.com') || window.location.href.includes('hubcdn.fans') || window.location.href.includes('hubcloud')) {

                                // 1. Check for generation button
                                let gen_btn = Array.from(document.querySelectorAll('a, button, .btn')).find(el => {
                                    let text = (el.innerText || "").toLowerCase();
                                    return text.includes('generate') || text.includes('direct download');
                                });
                                if (gen_btn && gen_btn.offsetParent !== null && !document.querySelector('.fsl_v2')) {
                                    gen_btn.click();
                                    return {action: "clicked_generate"};
                                }

                                // 2. Extract final links
                                let anchors = Array.from(document.querySelectorAll('a'));
                                for (let a of anchors) {
                                    let text = (a.innerText || "").toLowerCase();
                                    let href = a.href || "";
                                    let id = (a.id || "").toLowerCase();
                                    let cls = (a.className || "").toLowerCase();
                                    
                                    if (href.startsWith('http') && (
                                        text.includes('server') || 
                                        text.includes('download') || 
                                        text.includes('fsl') || 
                                        text.includes('pixel') || 
                                        text.includes('gbps') ||
                                        cls.includes('btn') ||
                                        ['s3', 'fsl', 'pixel', 'pixelserver'].includes(id)
                                    ) && !text.includes('generate') && !text.includes('share') && !href.includes('one.one.one.one')) {
                                        let label = a.innerText.trim() || id || "Download";
                                        // Avoid duplicates
                                        if (!d.links.find(l => l.url === href)) {
                                            d.links.push({label: label, url: href});
                                        }
                                    }
                                }
                                if (d.links.length > 0) d.success = true;
                            }

                            
                            // If we are on HubDrive (selection page)
                            if (!window.location.href.includes('gamerxyt.com') && !window.location.href.includes('hubcloud')) {
                                let hubcloud_btn = Array.from(document.querySelectorAll('a')).find(a => {
                                    let text = (a.innerText || "").toLowerCase();
                                    let href = a.href || "";
                                    return text.includes('hubcloud') || href.includes('hubcloud') || href.includes('gamerxyt');
                                });
                                if (hubcloud_btn) {
                                    hubcloud_btn.click();
                                    return {action: "clicked_hubcloud"};
                                }
                            }


                            return d;
                        }''')
                        
                        # Update metadata if found
                        if data.get("title") and data.get("title") != "Unknown": 
                            final_title = data["title"]
                        if data.get("size") and data.get("size") != "Unknown": 
                            final_size = data["size"]

                        
                        if data.get("action") in ["clicked_hubcloud", "clicked_generate"]:
                            logger.info(f"Action taken: {data['action']}, waiting...")
                            await hubdrive_page.wait_for_timeout(7000)
                            continue
                            
                        if data.get("success"):
                            logger.info("Successfully extracted HubCloud multi-links!")
                            return {
                                "type": "hubdrive_multi", 
                                "original": url, 
                                "title": final_title, 
                                "size": final_size, 
                                "links": data["links"], 
                                "success": True
                            }
                        
                        # If we have a direct download button but no multi-links yet, and it's not a selection/gen page
                        if not data.get("action") and not data.get("success"):
                            fallback_link = await hubdrive_page.evaluate('''() => {
                                let links = Array.from(document.querySelectorAll('a'));
                                for(let l of links) {
                                    let text = (l.innerText || "").toLowerCase();
                                    if(text.includes('direct') || text.includes('instant') || l.href.includes('direct') || l.href.includes('hubdrive.space/file/')) return l.href;
                                }
                                return null;
                            }''')
                            
                            # Only return fallback if it's a high-quality link or we are near the end
                            if fallback_link and (('hubdrive.space/file/' in hubdrive_page.url and 'hubcloud' not in hubdrive_page.url) or step > 15):
                                logger.info(f"Using fallback link: {fallback_link}")
                                return {"type": "hubdrive_direct", "original": url, "final": fallback_link, "title": final_title, "size": final_size, "success": True}
                            
                            logger.info("Nothing found on this page yet, continuing loop...")

                        
                    active_page = context.pages[-1]
                    
                    # Check for popups - Allow HubCloud and HubCDN
                    if not any(k in active_page.url for k in ['hblinks', 'cryptoinsights', 'gadgetsweb', 'hubdrive', 'gamerxyt', 'hubcloud', 'hubcdn']) and active_page != page:
                        logger.info(f"Closing suspected popup: {active_page.url}")
                        await active_page.close()
                        active_page = context.pages[-1]

                    
                    logger.info(f"Step {step} - Current URL: {active_page.url}")
                    
                    try:
                        # Priority 1: Direct HubDrive download link on intermediate landing pages (like hblinks.dad)
                        hub_link = await active_page.evaluate('''() => {
                            let a = document.querySelector('a[href*="hubdrive.space/file/"]');
                            if (a && a.offsetParent !== null) {
                                a.click();
                                return true;
                            }
                            return false;
                        }''')
                        if hub_link:
                            logger.info("Found HubDrive link on intermediate page, clicking...")
                            await active_page.wait_for_timeout(5000)
                            continue

                        # Priority 2: WP Safelink buttons (Only for non-HubDrive pages)
                        if not any(k in active_page.url for k in ['hubdrive', 'gamerxyt', 'hubcloud', 'hubcdn']):
                            clicked = await active_page.evaluate('''() => {
                                let selectors = [
                                    '#verify_btn', 'a.get-link', '#verify_button', '#generate_link', '#get_link',
                                    'a.btn', 'button', 'input[type="submit"]', 'a[class*="btn"]', 'a[id*="btn"]'
                                ];
                                for(let sel of selectors) {
                                    let elements = document.querySelectorAll(sel);
                                    for(let el of elements) {
                                        if(el.offsetParent !== null) {
                                            let text = (el.innerText || el.value || el.alt || "").toLowerCase();
                                            if(text.includes("continue") || text.includes("verify") || text.includes("get link") || text.includes("download") || text.includes("open") || text.includes("links")) {
                                                el.removeAttribute('target');
                                                el.click();
                                                return true;
                                            }
                                        }
                                    }
                                }
                                return false;
                            }''')
                            if clicked:
                                logger.info("Clicked WP Safelink button, waiting...")
                                await active_page.wait_for_timeout(10000)

                    except Exception as e:
                        logger.error(f"Error during step evaluation: {e}")

                return {"type": "wp_safelink", "original": url, "success": False, "error": "Could not bypass all timers within 12 steps."}
            except Exception as e:
                logger.error(f"Deep bypass error: {e}")
                return {"type": "wp_safelink", "original": url, "success": False, "error": str(e)}
            finally:
                await browser.close()
    except Exception as outer_e:
        logger.error(f"Playwright init error: {outer_e}")
        return {"type": "wp_safelink", "original": url, "success": False, "error": str(outer_e)}
    return {"type": "wp_safelink", "original": url, "success": False, "error": "Unknown Playwright context exit"}

async def resolve_link_smart(url: str) -> dict:
    # 0. Check if it's a known WP-Safelink that requires Deep Bypass
    if any(wp in url for wp in ["gadgetsweb.xyz", "cryptoinsights.site", "hblinks.dad", "hubdrive.space", "homelander"]):
        return await deep_bypass_wp_safelink(url)
        
    # 1. Check if shortener -> API bypass
    if is_shortener(url):
        bypassed = bypass_via_api(url)
        if bypassed != url:
            return {"type": "shortener", "original": url, "final": bypassed, "success": True}
        return {"type": "shortener", "original": url, "final": follow_redirects(url), "success": True}
        
    # 2. Check if already direct
    if is_direct_link(url):
        return {"type": "direct", "original": url, "final": url, "success": True}
        
    # 3. Use Playwright to scrape JS-heavy content pages like hdhub4u
    links = await scrape_with_playwright(url)
    if links:
        return {"type": "scraped", "original": url, "links": links, "success": True}
        
    # Fallback
    return {"type": "unknown", "original": url, "final": url, "success": False}

# ─── TELEGRAM UI ──────────────────────────────────────────────────────────────
def get_icon(url: str) -> str:
    domain = get_domain(url)
    if "drive.google" in domain: return "☁️ GDrive"
    if "mega" in domain: return "🟠 MEGA"
    if "mediafire" in domain: return "🔵 MediaFire"
    if "terabox" in domain: return "📦 TeraBox"
    if "pixeldrain" in domain: return "💧 PixelDrain"
    if "gofile" in domain: return "📁 GoFile"
    return "🔗 Link"

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = (
        "👋 *Link Bypass & Scraper Bot v3*\n\n"
        "🎬 *Movies & Series:* Send links from `hdhub4u`, `filmyzilla`, etc. I'll bypass JS protections and extract real download links.\n"
        "🔗 *Shorteners:* Send `LinkVertise`, `ShrinkMe`, `ADFly`. I'll find the direct destination.\n\n"
        "⚡ Send me any link to start!"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def handle_link(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    urls = re.findall(r'https?://[^\s]+', text)
    
    if not urls:
        await update.message.reply_text("⚠️ No URLs found in your message.")
        return
        
    url = urls[0].rstrip(".,;)'\"")
    
    proc = await update.message.reply_text(
        f"⏳ *Processing...*\n`{url[:60]}`\n\n_Using headless browser analysis..._",
        parse_mode="Markdown"
    )
    
    try:
        result = await resolve_link_smart(url)
        rtype = result["type"]
        
        if rtype == "scraped" and result["success"]:
            links = result["links"][:20]  # Take max 20
            
            text_lines = []
            keyboard = []
            
            for i, lnk in enumerate(links, 1):
                icon = get_icon(lnk["url"])
                short_url = lnk["url"][:40] + "..." if len(lnk["url"]) > 40 else lnk["url"]
                text_lines.append(f"*{i}.* {icon} {lnk['label']}\\n`{short_url}`")
                
                # Buttons
                keyboard.append([InlineKeyboardButton(f"{i}. {icon} {lnk['label']}"[:35], url=lnk["url"])])
                
            body = "\\n\\n".join(text_lines[0:8])  # Display top 8 in text
            if len(links) > 8:
                body += f"\\n\\n_...and {len(links)-8} more in buttons below._"
                
            await proc.edit_text(
                f"✅ *Extracted {len(links)} Links!*\n\n{body}",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard),
                disable_web_page_preview=True
            )
            
        elif rtype in ("shortener", "direct") and result["success"]:
            final = result["final"]
            icon = get_icon(final)
            await proc.edit_text(
                f"✅ *Bypassed!*\n\n{icon} *Final Link:*\n`{final}`\n\n🔍 Original: `{url[:40]}...`",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📥 Open Link", url=final)]]),
                disable_web_page_preview=True
            )
            
        elif rtype == "hubdrive_direct" and result["success"]:
            final = result.get("final", url)
            title = result.get("title", "Unknown")
            size = result.get("size", "Unknown")
            await proc.edit_text(
                f"✅ *HubDrive Found!*\n\n🎬 *{title}*\n📦 *Size:* {size}\n\n📥 *Link:*\n`{final}`",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📥 Download File", url=final)]]),
                disable_web_page_preview=True
            )
            
        elif rtype == "hubdrive_multi" and result["success"]:
            title = result.get("title", "Unknown")
            size = result.get("size", "Unknown")
            links = result["links"]
            
            kb = []
            txt_links = []
            for i, lnk in enumerate(links, 1):
                icon = get_icon(lnk["url"])
                txt_links.append(f"*{i}.* {icon} {lnk['label']}")
                kb.append([InlineKeyboardButton(f"{i}. {lnk['label']}"[:35], url=lnk["url"])])
            
            body = "\n".join(txt_links)
            await proc.edit_text(
                f"✅ *HubDrive Multi-Server Links!*\n\n🎬 *{title}*\n📦 *Size:* {size}\n\n{body}",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(kb),
                disable_web_page_preview=True
            )
            
        else:
            await proc.edit_text("❌ *No download links could be extracted.*\nThe site structure might be fully hidden or requires captcha.")
            
    except Exception as e:
        await proc.edit_text(f"❌ *Error occurred:*\n`{str(e)}`", parse_mode="Markdown")

def main():
    print("🚀 Initializing Bot Deployment...", flush=True)
    
    if check_telegram_api():
        print("✅ Telegram API is reachable from this server.", flush=True)
    else:
        print("⚠️ Warning: Telegram API is NOT reachable. Connection might be blocked.", flush=True)

    token_to_use = BOT_TOKEN
    if not token_to_use:
        print("❌ CRITICAL ERROR: BOT_TOKEN environment variable is not set!", flush=True)
        return

    truncated = token_to_use[:8] if len(token_to_use) >= 8 else token_to_use
    print(f"ℹ️ Using token starting with: {truncated}...", flush=True)


    # Increase timeouts to handle slow connections

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .get_updates_connect_timeout(30.0)
        .get_updates_read_timeout(30.0)
        .build()
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    print("🤖 Bot v3 started (Playwright Mode)", flush=True)

    try:
        app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        print("\n❌ Network Error: Failed to connect to Telegram servers.")
        print("💡 This is usually caused by an unstable internet connection or if Telegram is blocked in your country.")
        print("💡 Try using a VPN or proxy if your ISP blocks api.telegram.org.")


if __name__ == "__main__":
    main()
