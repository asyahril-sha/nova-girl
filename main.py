#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
GADIS AGI ULTIMATE V3.0 - MAIN ENTRY POINT
9 Role + MANTAN + TEMAN SMA dengan HTS/FWB System
"""

import os
import sys
import asyncio
import logging
from datetime import datetime
from pathlib import Path

# Setup path
sys.path.append(str(Path(__file__).parent))

# Flask
from flask import Flask, request, jsonify

# Telegram
from telegram import Update
from telegram.ext import Application
from telegram.request import HTTPXRequest

# Local imports
from config import Config
from database import Database
from systems.hts_fwb_system import HTSFWBSystem, RankingSystem
from tg_bot.handlers import TelegramHandlers
from tg_bot.commands import AdditionalCommands

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Buat folder yang diperlukan
Config.create_dirs()

# Flask app
flask_app = Flask(__name__)


class GadisUltimateBot:
    """
    Main bot class
    """
    
    def __init__(self):
        """Inisialisasi bot"""
        self.start_time = datetime.now()
        self.config = Config
        self.is_ready = False
        self.app = None
        
        # Validasi konfigurasi
        if not self.config.validate():
            logger.error("❌ Config validation failed")
            sys.exit(1)
        
        try:
            # Initialize database
            self.db = Database(Config.DB_PATH)
            logger.info("✅ Database initialized")
            
            # Initialize systems
            self.hts_system = HTSFWBSystem(self.db)
            self.ranking = RankingSystem(self.db)
            
            # Initialize handlers
            self.handlers = TelegramHandlers(self)
            
            logger.info("✅ Bot initialized")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize bot: {e}")
            sys.exit(1)
    
    async def initialize(self):
        """Initialize bot application"""
        try:
            # Setup request dengan timeout
            request = HTTPXRequest(
                connection_pool_size=20,
                connect_timeout=60,
                read_timeout=60,
                write_timeout=60
            )
            
            # Build application
            self.app = (
                Application.builder()
                .token(self.config.TELEGRAM_TOKEN)
                .request(request)
                .build()
            )
            
            # Register handlers
            await self.handlers.setup(self.app)
            
            # Initialize
            await self.app.initialize()
            self.is_ready = True
            
            logger.info("✅ Application initialized")
            return self.app
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize application: {e}")
            sys.exit(1)
    
    def get_uptime(self) -> str:
        """Dapatkan uptime bot"""
        delta = datetime.now() - self.start_time
        days = delta.days
        hours = delta.seconds // 3600
        minutes = (delta.seconds // 60) % 60
        
        parts = []
        if days > 0:
            parts.append(f"{days} hari")
        if hours > 0:
            parts.append(f"{hours} jam")
        if minutes > 0:
            parts.append(f"{minutes} menit")
        
        return " ".join(parts) if parts else "beberapa detik"


# Buat instance bot (di luar class)
bot = GadisUltimateBot()


# ============================================================================
# FLASK ROUTES
# ============================================================================

@flask_app.route('/webhook', methods=['POST'])
def webhook():
    """Webhook endpoint untuk Telegram"""
    if not bot.is_ready:
        logger.warning("Webhook called but bot not ready")
        return jsonify({'error': 'Bot not ready'}), 503
    
    try:
        update_data = request.get_json(force=True)
        update_id = update_data.get('update_id', 'unknown')
        
        logger.debug(f"📥 Webhook received - Update ID: {update_id}")
        
        # Buat update object
        update = Update.de_json(update_data, bot.app.bot)
        
        # Proses update di event loop yang sama
        asyncio.run_coroutine_threadsafe(
            bot.app.process_update(update),
            asyncio.get_event_loop()
        )
        
        return 'OK', 200
    
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({'error': str(e)}), 500


@flask_app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'bot_ready': bot.is_ready,
        'version': '3.0',
        'timestamp': datetime.now().isoformat()
    })


@flask_app.route('/')
def home():
    """Home endpoint"""
    return jsonify({
        'message': 'GADIS AGI ULTIMATE V3.0 is running!',
        'version': '3.0',
        'features': [
            '9 Role (termasuk MANTAN dan TEMAN SMA)',
            'HTS/FWB System dengan Unique ID',
            'TOP 10 Ranking',
            'Level 1-12 + Reset ke 7',
            'Memory System',
            'Emotional Engine',
            'Consciousness Loop'
        ],
        'endpoints': ['/health', '/webhook'],
        'status': 'online',
        'timestamp': datetime.now().isoformat()
    })


@flask_app.route('/test')
def test():
    """Test endpoint"""
    return jsonify({
        'status': 'ok',
        'message': 'Server is running',
        'bot': {
            'ready': bot.is_ready,
            'uptime': bot.get_uptime()
        }
    })


# ============================================================================
# MAIN
# ============================================================================

async def setup():
    """Setup bot dan webhook"""
    global bot
    
    print("\n" + "="*60)
    print("🚀 GADIS AGI ULTIMATE V3.0")
    print("="*60)
    print("\n📋 Features:")
    print("  • 9 Role (termasuk MANTAN & TEMAN SMA)")
    print("  • HTS/FWB System dengan Unique ID")
    print("  • TOP 10 Ranking")
    print("  • Level 1-12 + Reset ke 7")
    print("  • Memory System")
    print("  • Emotional Engine")
    print("  • Consciousness Loop")
    print("\n" + "="*60)
    
    # Initialize bot
    await bot.initialize()
    
    # Set webhook jika di Railway
    railway_url = os.getenv('RAILWAY_PUBLIC_DOMAIN') or os.getenv('RAILWAY_STATIC_URL')
    if railway_url:
        webhook_url = f"https://{railway_url}/webhook"
        
        # Set webhook
        await bot.app.bot.set_webhook(url=webhook_url)
        logger.info(f"✅ Webhook set to {webhook_url}")
        
        # Test webhook
        webhook_info = await bot.app.bot.get_webhook_info()
        logger.info(f"📋 Webhook info: {webhook_info.url}")
    else:
        logger.warning("⚠️ RAILWAY_PUBLIC_DOMAIN not set, webhook not configured")
    
    print("\n" + "="*60)
    print("✅ Bot is running!")
    print("="*60 + "\n")
    
    return bot


def run():
    """Run the bot"""
    # Setup event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Setup bot
    loop.run_until_complete(setup())
    
    # Run Flask
    port = int(os.getenv('PORT', 8080))
    print(f"\n🌐 Starting web server on port {port}")
    print(f"📡 Webhook endpoint: /webhook")
    print(f"💚 Health check: /health")
    print(f"🧪 Test endpoint: /test")
    print("\n" + "="*60)
    
    flask_app.run(host='0.0.0.0', port=port, debug=False)


if __name__ == "__main__":
    run()
