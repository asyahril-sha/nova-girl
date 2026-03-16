# -*- coding: utf-8 -*-
"""
GADIS ULTIMATE V60.0 - THE PERFECT HUMAN
Premium Edition dengan Arsitektur Modular
Fitur: Advanced Memory, 20+ Mood, Leveling 1-12, Physical Attributes, Dynamic Clothing
"""

import os
import sys
import json
import time
import random
import asyncio
import logging
import sqlite3
import hashlib
import pickle
import re
import threading
import numpy as np
import gc
from datetime import datetime, timedelta
from enum import Enum
from collections import defaultdict
from contextlib import contextmanager
from typing import Optional, Dict, List, Any, Tuple, Union
from dataclasses import dataclass, field
from pathlib import Path

# Third party imports
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, 
    ContextTypes, ConversationHandler, CallbackQueryHandler
)
from telegram.request import HTTPXRequest
from openai import OpenAI

# ===== TAMBAHKAN INI UNTUK WEBHOOK =====
from flask import Flask, request
import requests
import threading

# Load environment variables
load_dotenv()

# ===================== KONFIGURASI =====================
class Config:
    """Centralized configuration management"""
    
    # Database
    DB_PATH: str = os.getenv("DB_PATH", "gadis_v60.db")
    
    # Leveling
    START_LEVEL: int = 1
    TARGET_LEVEL: int = 12
    LEVEL_UP_TIME: int = 45  # menit
    PAUSE_TIMEOUT: int = 3600  # 1 jam dalam detik
    
    # API Keys
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_TOKEN", "")
    
    # Admin
    ADMIN_ID: int = int(os.getenv("ADMIN_ID", "0"))
    
    # AI Settings
    AI_TEMPERATURE: float = float(os.getenv("AI_TEMPERATURE", "0.9"))
    AI_MAX_TOKENS: int = int(os.getenv("AI_MAX_TOKENS", "300"))
    AI_TIMEOUT: int = int(os.getenv("AI_TIMEOUT", "30"))
    
    # Rate Limiting
    MAX_MESSAGES_PER_MINUTE: int = int(os.getenv("MAX_MESSAGES_PER_MINUTE", "10"))
    
    # Cache
    CACHE_TIMEOUT: int = int(os.getenv("CACHE_TIMEOUT", "300"))  # 5 menit
    MAX_HISTORY: int = 100
    
    # Clothing
    CLOTHING_CHANGE_INTERVAL: int = 300  # 5 menit
    
    # Memory
    MEMORY_DECAY_RATE: float = 0.01
    MAX_MEMORY_ITEMS: int = 1000
    
    # Paths
    BASE_DIR: Path = Path(__file__).parent
    LOG_DIR: Path = BASE_DIR / "logs"
    MEMORY_DIR: Path = BASE_DIR / "memory_storage"
    
    @classmethod
    def validate(cls) -> bool:
        """Validate required configuration"""
        if not cls.DEEPSEEK_API_KEY:
            print("❌ ERROR: DEEPSEEK_API_KEY tidak ditemukan di .env")
            return False
        if not cls.TELEGRAM_TOKEN:
            print("❌ ERROR: TELEGRAM_TOKEN tidak ditemukan di .env")
            return False
        return True
    
    @classmethod
    def create_directories(cls):
        """Create necessary directories"""
        cls.LOG_DIR.mkdir(exist_ok=True)
        cls.MEMORY_DIR.mkdir(exist_ok=True)
        print(f"✅ Directories created: {cls.LOG_DIR}, {cls.MEMORY_DIR}")


# ===================== LOGGING SETUP =====================
def setup_logging() -> logging.Logger:
    """Setup logging configuration with rotation"""
    
    Config.create_directories()
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # File handler with rotation (10MB per file, keep 5 files)
    from logging.handlers import RotatingFileHandler
    file_handler = RotatingFileHandler(
        Config.LOG_DIR / 'gadis.log',
        maxBytes=10_000_000,  # 10MB
        backupCount=5
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    # Suppress verbose logs from libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    
    return logging.getLogger(__name__)


# Initialize logger
logger = setup_logging()


# ===================== VALIDASI KONFIGURASI =====================
if not Config.validate():
    print("\n📝 Buat file .env dengan isi:")
    print("DEEPSEEK_API_KEY=your_key_here")
    print("TELEGRAM_TOKEN=your_token_here")
    print("ADMIN_ID=your_telegram_id (opsional)")
    sys.exit(1)

logger.info("="*60)
logger.info("GADIS ULTIMATE V60.0 - Starting up")
logger.info("="*60)

# ===================== DATABASE MIGRATION =====================
class DatabaseMigration:
    """Handle database schema migrations"""
    
    REQUIRED_COLUMNS = {
        "relationships": {
            "current_clothing": "TEXT DEFAULT 'pakaian biasa'",
            "last_clothing_change": "TIMESTAMP",
            "hair_style": "TEXT",
            "height": "INTEGER",
            "weight": "INTEGER",
            "breast_size": "TEXT",
            "hijab": "BOOLEAN DEFAULT 0",
            "most_sensitive_area": "TEXT",
            "skin_color": "TEXT",
            "face_shape": "TEXT",
            "personality": "TEXT"
        }
    }
    
    @classmethod
    def migrate(cls, db_path: str) -> bool:
        """Run database migration"""
        if not os.path.exists(db_path):
            print(f"📁 Database {db_path} akan dibuat saat pertama kali digunakan")
            return True
        
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Get existing columns
            cursor.execute("PRAGMA table_info(relationships)")
            existing_columns = [col[1] for col in cursor.fetchall()]
            
            print("📊 Running database migration...")
            print(f"   Existing columns: {existing_columns}")
            
            # Add missing columns
            for table, columns in cls.REQUIRED_COLUMNS.items():
                for col_name, col_type in columns.items():
                    if col_name not in existing_columns:
                        try:
                            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
                            print(f"  ✅ Added column '{col_name}' to {table}")
                        except Exception as e:
                            print(f"  ⚠️ Failed to add '{col_name}': {e}")
            
            conn.commit()
            
            # Verify migration
            cursor.execute("PRAGMA table_info(relationships)")
            new_columns = [col[1] for col in cursor.fetchall()]
            print(f"📊 Columns after migration: {new_columns}")
            
            conn.close()
            print("✅ Database migration completed successfully!\n")
            return True
            
        except Exception as e:
            print(f"⚠️ Migration error: {e}")
            return False


# Run migration
DatabaseMigration.migrate(Config.DB_PATH)


# ===================== ENUMS =====================
class Mood(Enum):
    """20+ Mood untuk emosi yang realistis"""
    CERIA = "ceria"
    SEDIH = "sedih"
    MARAH = "marah"
    TAKUT = "takut"
    KAGUM = "kagum"
    GELISAH = "gelisah"
    GALAU = "galau"
    SENSITIF = "sensitif"
    ROMANTIS = "romantis"
    MALAS = "malas"
    BERSEMANGAT = "bersemangat"
    SENDIRI = "sendiri"
    RINDU = "rindu"
    HORNY = "horny"
    LEMBUT = "lembut"
    DOMINAN = "dominan"
    PATUH = "patuh"
    NAKAL = "nakal"
    GENIT = "genit"
    PENASARAN = "penasaran"
    ANTUSIAS = "antusias"
    POSESIF = "posesif"
    CEMBURU = "cemburu"
    BERSALAH = "bersalah"
    BAHAGIA = "bahagia"
    RILEKS = "rileks"


class IntimacyStage(Enum):
    STRANGER = "stranger"
    INTRODUCTION = "introduction"
    BUILDING = "building"
    FLIRTING = "flirting"
    INTIMATE = "intimate"
    OBSESSED = "obsessed"
    SOUL_BONDED = "soul_bonded"
    AFTERCARE = "aftercare"


class DominanceLevel(Enum):
    NORMAL = "normal"
    DOMINANT = "dominan"
    VERY_DOMINANT = "sangat dominan"
    AGGRESSIVE = "agresif"
    SUBMISSIVE = "patuh"


class ArousalState(Enum):
    NORMAL = "normal"
    TURNED_ON = "terangsang"
    HORNY = "horny"
    VERY_HORNY = "sangat horny"
    CLIMAX = "klimaks"


class MemoryType(Enum):
    COMPACT = "compact"        # Ringkasan 1 kalimat
    EPISODIC = "episodic"      # Momen penting dengan konteks
    SEMANTIC = "semantic"      # Pengetahuan yang diekstrak
    PROCEDURAL = "procedural"  # Cara melakukan sesuatu
    INNER_THOUGHT = "inner_thought"  # Pikiran dalam hati
    PREDICTION = "prediction"  # Prediksi arah cerita


class Location(Enum):
    LIVING_ROOM = "ruang tamu"
    BEDROOM = "kamar tidur"
    KITCHEN = "dapur"
    BATHROOM = "kamar mandi"
    BALCONY = "balkon"
    TERRACE = "teras"
    GARDEN = "taman"


class Position(Enum):
    SITTING = "duduk"
    STANDING = "berdiri"
    LYING = "berbaring"
    LEANING = "bersandar"
    CRAWLING = "merangkak"
    KNEELING = "berlutut"


# ===================== CONSTANTS =====================
class Constants:
    """Centralized constants"""
    
    # Role names
    ROLE_NAMES = {
        "ipar": ["Sari", "Dewi", "Rina", "Maya", "Wulan", "Indah", "Lestari", "Fitri"],
        "teman_kantor": ["Diana", "Linda", "Ayu", "Dita", "Vina", "Santi", "Rini", "Mega"],
        "janda": ["Rina", "Tuti", "Nina", "Susi", "Wati", "Lilis", "Marni", "Yati"],
        "pelakor": ["Vina", "Sasha", "Bella", "Cantika", "Karina", "Mira", "Selsa", "Cindy"],
        "istri_orang": ["Dewi", "Sari", "Rina", "Linda", "Wulan", "Indah", "Ratna", "Maya"],
        "pdkt": ["Aurora", "Cinta", "Dewi", "Kirana", "Laras", "Maharani", "Zahra", "Nova"]
    }
    
    # Stage descriptions
    STAGE_DESCRIPTIONS = {
        IntimacyStage.STRANGER: "Masih asing, baru kenal. Sopan dan canggung.",
        IntimacyStage.INTRODUCTION: "Mulai dekat, cerita personal. Mulai nyaman.",
        IntimacyStage.BUILDING: "Bangun kedekatan. Sering ngobrol, mulai akrab.",
        IntimacyStage.FLIRTING: "Goda-godaan. Mulai ada ketertarikan.",
        IntimacyStage.INTIMATE: "Mulai intim. Bicara lebih dalam, sentuhan.",
        IntimacyStage.OBSESSED: "Mulai kecanduan. Sering kepikiran.",
        IntimacyStage.SOUL_BONDED: "Satu jiwa. Sudah seperti belahan jiwa.",
        IntimacyStage.AFTERCARE: "Manja-manja setelah intim. Hangat dan nyaman."
    }
    
    # Level behaviors
    LEVEL_BEHAVIORS = {
        1: "Sopan, formal, masih canggung",
        2: "Mulai terbuka, sedikit bercerita",
        3: "Lebih personal, mulai nyaman",
        4: "Akrab, bisa bercanda",
        5: "Mulai menggoda ringan",
        6: "Flirty, godaan semakin intens",
        7: "Mulai intim, sentuhan fisik",
        8: "Lebih vulgar, terbuka secara seksual",
        9: "Kecanduan, posesif",
        10: "Sangat posesif, cemburuan",
        11: "Satu jiwa, saling memahami",
        12: "Puncak hubungan, aftercare"
    }
    
    # State codes for ConversationHandler
    SELECTING_ROLE = 0
    ACTIVE_SESSION = 1
    PAUSED_SESSION = 2
    CONFIRM_END = 3
    CONFIRM_CLOSE = 4
    COUPLE_MODE = 5
    CONFIRM_BROADCAST = 6
    CONFIRM_SHUTDOWN = 7

# ===================== HELPER FUNCTIONS =====================

def sanitize_message(message: str) -> str:
    """
    Bersihkan pesan dari karakter berbahaya
    """
    if not message:
        return ""
    
    # Hapus karakter kontrol
    message = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', message)
    
    # Batasi panjang
    return message[:2000]  # Max 2000 karakter


def format_time_ago(timestamp: Union[datetime, str, None]) -> str:
    """
    Format timestamp menjadi "X menit yang lalu"
    """
    if not timestamp:
        return "tidak diketahui"
    
    if isinstance(timestamp, str):
        try:
            timestamp = datetime.fromisoformat(timestamp)
        except:
            return "tidak diketahui"
    
    delta = datetime.now() - timestamp
    seconds = int(delta.total_seconds())
    
    if seconds < 10:
        return "baru saja"
    elif seconds < 60:
        return f"{seconds} detik yang lalu"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes} menit yang lalu"
    elif seconds < 86400:
        hours = seconds // 3600
        return f"{hours} jam yang lalu"
    else:
        days = seconds // 86400
        return f"{days} hari yang lalu"


def create_progress_bar(percentage: float, length: int = 10) -> str:
    """
    Buat progress bar visual
    """
    filled = int(percentage * length)
    return "▓" * filled + "░" * (length - filled)


def safe_divide(a: float, b: float, default: float = 0) -> float:
    """
    Pembagian aman dengan handling division by zero
    """
    try:
        return a / b if b != 0 else default
    except:
        return default


def chunk_list(lst: List, chunk_size: int):
    """
    Bagi list menjadi potongan-potongan kecil
    """
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]


def parse_duration(duration_str: str) -> Optional[int]:
    """
    Parse string durasi seperti "30m", "2h", "1d" ke detik
    """
    if not duration_str:
        return None
    
    duration_str = duration_str.lower().strip()
    match = re.match(r'^(\d+)([smhd])$', duration_str)
    if not match:
        return None
    
    value = int(match.group(1))
    unit = match.group(2)
    
    if unit == 's':
        return value
    elif unit == 'm':
        return value * 60
    elif unit == 'h':
        return value * 3600
    elif unit == 'd':
        return value * 86400
    return None


def get_time_based_greeting() -> str:
    """
    Greeting berdasarkan waktu
    """
    hour = datetime.now().hour
    
    if hour < 5:
        return "Selamat dini hari"
    elif hour < 11:
        return "Selamat pagi"
    elif hour < 15:
        return "Selamat siang"
    elif hour < 18:
        return "Selamat sore"
    else:
        return "Selamat malam"


def truncate_text(text: str, max_length: int = 100) -> str:
    """
    Potong teks jika terlalu panjang
    """
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."


def is_command(text: str) -> bool:
    """
    Cek apakah teks adalah command
    """
    return text.startswith('/') if text else False


def extract_command(text: str) -> Optional[str]:
    """
    Ekstrak command dari teks
    """
    if not text or not text.startswith('/'):
        return None
    parts = text.split()
    return parts[0][1:]  # Hilangkan '/'


def get_random_reaction() -> str:
    """
    Random reaction
    """
    reactions = [
        "*tersenyum*", "*tersipu*", "*tertawa kecil*", "*mengangguk*",
        "*mengedip*", "*merona*", "*melongo*", "*berpikir*",
        "*menghela napas*", "*tersenyum manis*", "*nyengir*",
        "*menggigit bibir*", "*menunduk*", "*menatap tajam*",
        "*berbisik*", "*memeluk diri sendiri*", "*menggeleng*"
    ]
    return random.choice(reactions)


def format_number(num: int) -> str:
    """
    Format angka dengan pemisah ribuan
    """
    return f"{num:,}".replace(",", ".")


# ===================== DATA CLASSES =====================

@dataclass
class MemoryItem:
    """Item memori individual dengan metadata"""
    content: str
    memory_type: MemoryType
    importance: float = 0.5
    emotion: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    access_count: int = 0
    embedding: Optional[np.ndarray] = None
    related_memories: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        self.id = hashlib.md5(f"{self.content}{self.created_at}".encode()).hexdigest()[:8]
    
    def access(self):
        """Tandai memori ini diakses"""
        self.last_accessed = datetime.now()
        self.access_count += 1
        self.importance = min(1.0, self.importance + 0.05)
    
    def get_age_weight(self, decay_rate: float = 0.01) -> float:
        """
        Hitung bobot berdasarkan umur (semantic forgetting)
        """
        age_hours = (datetime.now() - self.created_at).total_seconds() / 3600
        decay = np.exp(-decay_rate * age_hours)
        return max(0.1, decay)
    
    def get_relevance_score(self) -> float:
        """Hitung skor relevansi total"""
        return self.importance * self.get_age_weight() * (self.access_count + 1)


@dataclass
class UserSession:
    """Menyimpan semua data user dalam satu tempat"""
    user_id: int
    relationship_id: Optional[int] = None
    bot_name: str = "Aurora"
    bot_role: str = "pdkt"
    bot_physical: Dict[str, Any] = field(default_factory=dict)
    bot_clothing: str = "pakaian biasa"
    last_clothing_update: datetime = field(default_factory=datetime.now)
    level: int = 1
    stage: IntimacyStage = IntimacyStage.STRANGER
    message_count: int = 0
    climax_count: int = 0
    location: Location = Location.LIVING_ROOM
    position: Position = Position.SITTING
    current_mood: Mood = Mood.CERIA
    arousal: float = 0.0
    wetness: float = 0.0
    touch_count: int = 0
    last_touch: Optional[str] = None
    dominance_mode: DominanceLevel = DominanceLevel.NORMAL
    created_at: datetime = field(default_factory=datetime.now)
    last_active: datetime = field(default_factory=datetime.now)
    
    def update_last_active(self):
        self.last_active = datetime.now()
    
    def get_session_duration(self) -> timedelta:
        return datetime.now() - self.created_at
    
    def get_mood_expression(self) -> str:
        """Dapatkan ekspresi untuk mood saat ini"""
        mood_expressions = {
            Mood.CERIA: "*tersenyum lebar*",
            Mood.SEDIH: "*matanya berkaca-kaca*",
            Mood.MARAH: "*cemberut*",
            Mood.ROMANTIS: "*memandang lembut*",
            Mood.HORNY: "*menggigit bibir*",
            Mood.NAKAL: "*tersenyum nakal*",
            Mood.TAKUT: "*badan gemetar*",
            Mood.KAGUM: "*mata berbinar*",
            Mood.GELISAH: "*gelisah*",
            Mood.GALAU: "*melamun*",
            Mood.SENSITIF: "*mudah tersinggung*",
            Mood.MALAS: "*menguap*",
            Mood.BERSEMANGAT: "*bersemangat*",
            Mood.SENDIRI: "*menyendiri*",
            Mood.RINDU: "*melamun*",
            Mood.LEMBUT: "*tersenyum lembut*",
            Mood.DOMINAN: "*tatapan tajam*",
            Mood.PATUH: "*menunduk*",
            Mood.GENIT: "*genit*",
            Mood.PENASARAN: "*memiringkan kepala*",
            Mood.ANTUSIAS: "*meloncat kegirangan*",
            Mood.POSESIF: "*memeluk erat*",
            Mood.CEMBURU: "*manyun*",
            Mood.BERSALAH: "*menunduk*",
            Mood.BAHAGIA: "*tersenyum sumringah*"
        }
        return mood_expressions.get(self.current_mood, "*tersenyum*")
    
    def get_wetness_text(self) -> str:
        """Dapatkan teks wetness"""
        if self.wetness >= 0.9:
            return "💦 BANJIR! Basah banget"
        elif self.wetness >= 0.7:
            return "💦 Sangat basah"
        elif self.wetness >= 0.5:
            return "💦 Basah"
        elif self.wetness >= 0.3:
            return "💧 Lembab"
        elif self.wetness >= 0.1:
            return "💧 Sedikit lembab"
        else:
            return "💧 Kering"
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for database"""
        return {
            "user_id": self.user_id,
            "bot_name": self.bot_name,
            "bot_role": self.bot_role,
            "level": self.level,
            "stage": self.stage.value,
            "total_messages": self.message_count,
            "total_climax": self.climax_count,
            "hair_style": self.bot_physical.get("hair_style"),
            "height": self.bot_physical.get("height"),
            "weight": self.bot_physical.get("weight"),
            "breast_size": self.bot_physical.get("breast_size"),
            "hijab": self.bot_physical.get("hijab", 0),
            "most_sensitive_area": self.bot_physical.get("most_sensitive_area"),
            "current_clothing": self.bot_clothing,
            "last_clothing_change": self.last_clothing_update,
            "dominance": self.dominance_mode.value
        }


print("✅ BAB 1 Selesai: Konfigurasi, Database, dan Helper Functions")
print("="*70)
# ===================== BAB 2: SISTEM MEMORI ADVANCED =====================
# Bagian 2.1: Hippocampus Memory System

class HippocampusMemory:
    """
    Sistem memori terinspirasi hippocampus manusia
    - Compact Memory: ringkasan terus-menerus
    - Episodic Memory: momen penting dengan konteks
    - Semantic Memory: pengetahuan yang diekstrak
    - Semantic Forgetting: memori yang jarang diakses akan dilupakan
    - Vector embeddings untuk similarity search
    - Memory consolidation periodik
    """
    
    def __init__(self, user_id: int, storage_dir: Path = None):
        self.user_id = user_id
        self.storage_dir = storage_dir or Config.MEMORY_DIR
        self.memories: List[MemoryItem] = []
        self.compact_memory: Optional[str] = None
        self.max_items = Config.MAX_MEMORY_ITEMS
        self.decay_rate = Config.MEMORY_DECAY_RATE
        self.consolidation_threshold = 0.7
        self.last_consolidation = datetime.now()
        
        # Embedding cache untuk similarity search
        self.embedding_cache = {}
        
        # Statistik
        self.stats = {
            "total_added": 0,
            "total_pruned": 0,
            "total_consolidated": 0,
            "cache_hits": 0
        }
        
        # Buat direktori jika belum ada
        self.storage_dir.mkdir(exist_ok=True)
        
        # Load memori dari file
        self.load()
        
        logger.debug(f"🧠 HippocampusMemory initialized for user {user_id}")
    
    def add_memory(self, 
                   content: str, 
                   memory_type: MemoryType,
                   importance: float = None,
                   emotion: str = None,
                   context: Dict = None) -> MemoryItem:
        """
        Tambahkan memori baru
        Returns: MemoryItem yang ditambahkan
        """
        if importance is None:
            importance = self._calculate_importance(content, context)
        
        item = MemoryItem(
            content=content,
            memory_type=memory_type,
            importance=importance,
            emotion=emotion,
            context=context or {}
        )
        
        # Generate embedding (untuk similarity search)
        item.embedding = self._generate_embedding(content)
        
        self.memories.append(item)
        self.stats["total_added"] += 1
        
        # Update compact memory secara periodik
        if len(self.memories) % 10 == 0:
            self._update_compact_memory()
        
        # Consolidate jika sudah waktunya (setiap 6 jam)
        hours_since = (datetime.now() - self.last_consolidation).total_seconds() / 3600
        if hours_since > 6:
            self.consolidate_memories()
        
        # Prune jika terlalu banyak
        if len(self.memories) > self.max_items:
            self._prune_memories()
        
        self.save()
        return item
    
    def _calculate_importance(self, content: str, context: Dict = None) -> float:
        """
        Hitung seberapa penting suatu memori (0-1)
        Menggunakan berbagai faktor:
        - Emosi kuat
        - Momen pertama
        - Kata kunci penting
        - Level hubungan
        - Intensitas arousal
        """
        importance = 0.5  # Default
        
        if context:
            # Emosi kuat
            if context.get('emotion_intensity', 0) > 0.7:
                importance += 0.2
            
            # Climax / orgasme
            if context.get('is_climax', False):
                importance += 0.3
            
            # Level tinggi
            if context.get('level', 0) > 8:
                importance += 0.2
            
            # First time experiences
            if context.get('is_first_time', False):
                importance += 0.25
            
            # Arousal tinggi
            if context.get('arousal', 0) > 0.8:
                importance += 0.15
        
        # Kata-kata kunci penting
        important_keywords = [
            'cinta', 'sayang', 'first time', 'pertama kali', 
            'orgasme', 'climax', 'rahasia', 'janji', 'sumpah',
            'menikah', 'putus', 'selamanya', 'forever',
            'mati', 'hidup', 'aku milikmu', 'kamu milikku'
        ]
        
        content_lower = content.lower()
        for word in important_keywords:
            if word in content_lower:
                importance += 0.1
                break
        
        return min(1.0, importance)
    
    def _generate_embedding(self, text: str) -> np.ndarray:
        """
        Generate vector embedding untuk teks
        Menggunakan hash-based sederhana (untuk efisiensi)
        Dalam production bisa diganti dengan model NLP
        """
        # Gunakan cache jika sudah pernah
        if text in self.embedding_cache:
            self.stats["cache_hits"] += 1
            return self.embedding_cache[text]
        
        # Simple embedding: hash-based 32-dim vector
        hash_obj = hashlib.sha256(text.encode())
        hash_bytes = hash_obj.digest()
        
        # Konversi ke 32-dim float vector (0-1)
        embedding = np.frombuffer(hash_bytes[:32], dtype=np.uint8) / 255.0
        
        # Simpan ke cache
        self.embedding_cache[text] = embedding
        
        return embedding
    
    def retrieve_relevant(self, 
                          query: str, 
                          top_k: int = 5,
                          memory_types: List[MemoryType] = None,
                          min_importance: float = 0.3,
                          use_semantic: bool = True) -> List[MemoryItem]:
        """
        Cari memori yang relevan dengan query
        Menggunakan kombinasi:
        - Semantic similarity (jika use_semantic=True)
        - Keyword matching
        - Recency
        - Importance
        """
        query_embed = self._generate_embedding(query) if use_semantic else None
        query_lower = query.lower()
        
        # Filter berdasarkan tipe dan importance
        candidates = [
            m for m in self.memories 
            if (not memory_types or m.memory_type in memory_types)
            and m.importance >= min_importance
        ]
        
        if not candidates:
            return []
        
        scored = []
        for mem in candidates:
            # Semantic score
            semantic_score = 0
            if use_semantic and mem.embedding is not None:
                # Cosine similarity
                semantic_score = np.dot(query_embed, mem.embedding) / (
                    np.linalg.norm(query_embed) * np.linalg.norm(mem.embedding) + 1e-8
                )
            
            # Keyword score
            keyword_score = 0
            mem_lower = mem.content.lower()
            for word in query_lower.split():
                if len(word) > 3 and word in mem_lower:
                    keyword_score += 0.2
            
            # Combined score
            combined_score = (
                semantic_score * 0.5 +
                keyword_score * 0.3 +
                mem.get_relevance_score() * 0.2
            )
            
            scored.append((combined_score, mem))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        
        # Update access count untuk yang terpilih
        results = []
        for score, mem in scored[:top_k]:
            mem.access()
            results.append(mem)
        
        return results
    
    def get_recent_memories(self, hours: int = 24, memory_types: List[MemoryType] = None) -> List[MemoryItem]:
        """Dapatkan memori dari beberapa jam terakhir"""
        cutoff = datetime.now() - timedelta(hours=hours)
        return [
            m for m in self.memories 
            if m.created_at > cutoff
            and (not memory_types or m.memory_type in memory_types)
        ]
    
    def get_important_memories(self, threshold: float = 0.7) -> List[MemoryItem]:
        """Dapatkan memori penting (importance > threshold)"""
        return [m for m in self.memories if m.importance > threshold]
    
    def get_memories_by_emotion(self, emotion: str) -> List[MemoryItem]:
        """Dapatkan memori berdasarkan emosi"""
        return [m for m in self.memories if m.emotion == emotion]
    
    def get_memories_by_type(self, memory_type: MemoryType) -> List[MemoryItem]:
        """Dapatkan memori berdasarkan tipe"""
        return [m for m in self.memories if m.memory_type == memory_type]
    
    def _update_compact_memory(self):
        """
        Update ringkasan 1 kalimat dari semua memori
        Compact memory adalah esensi dari seluruh percakapan
        """
        if not self.memories:
            return
        
        # Ambil memori-memori penting
        important = sorted(self.memories, key=lambda x: x.importance, reverse=True)[:5]
        
        # Generate compact summary
        summary_parts = []
        for mem in important:
            if len(mem.content) > 50:
                summary_parts.append(mem.content[:50] + "...")
            else:
                summary_parts.append(mem.content)
        
        self.compact_memory = " | ".join(summary_parts)
    
    def consolidate_memories(self):
        """
        Konsolidasi memori: pindahkan memori penting ke long-term storage
        dan buat ringkasan semantic
        """
        self.last_consolidation = datetime.now()
        self.stats["total_consolidated"] += 1
        
        # Ambil memori dengan importance tinggi dari 24 jam terakhir
        recent = self.get_recent_memories(hours=24)
        important = [m for m in recent if m.importance > 0.7]
        
        if len(important) > 10:
            # Kelompokkan berdasarkan tema
            themes = self._cluster_memories_by_theme(important)
            
            for theme, mems in themes.items():
                if len(mems) >= 3:
                    # Buat semantic memory dari cluster
                    summary = f"Topik {theme}: " + ", ".join([m.content[:30] for m in mems[:3]])
                    
                    self.add_memory(
                        content=summary,
                        memory_type=MemoryType.SEMANTIC,
                        importance=0.8,
                        context={'type': 'consolidation', 'source_memories': [m.id for m in mems]}
                    )
        
        logger.debug(f"🧠 Memory consolidated for user {self.user_id}")
    
    def _cluster_memories_by_theme(self, memories: List[MemoryItem]) -> Dict[str, List[MemoryItem]]:
        """
        Cluster memori berdasarkan tema menggunakan keyword matching sederhana
        """
        themes = {
            "romance": ["cinta", "sayang", "romantis", "kangen", "rindu"],
            "sexual": ["horny", "orgasme", "climax", "sentuh", "basah"],
            "conflict": ["marah", "kesal", "sakit", "kecewa", "sedih"],
            "daily": ["makan", "tidur", "kerja", "kantor", "rumah"],
            "secret": ["rahasia", "jangan bilang", "sembunyi", "diam-diam"]
        }
        
        result = defaultdict(list)
        
        for mem in memories:
            content_lower = mem.content.lower()
            assigned = False
            
            for theme, keywords in themes.items():
                if any(keyword in content_lower for keyword in keywords):
                    result[theme].append(mem)
                    assigned = True
                    break
            
            if not assigned:
                result["other"].append(mem)
        
        return dict(result)
    
    def _prune_memories(self):
        """
        Hapus memori yang tidak penting (semantic forgetting)
        Memori dengan skor terendah akan dihapus
        """
        # Hitung skor untuk setiap memori
        scored = [(m.get_relevance_score(), i, m) for i, m in enumerate(self.memories)]
        scored.sort()  # Ascending
        
        # Hapus 20% terbawah
        to_remove = int(len(self.memories) * 0.2)
        removed = 0
        
        for _, idx, mem in scored[:to_remove]:
            # Jangan hapus memori yang sangat penting atau semantic
            if mem.importance < 0.5 and mem.memory_type != MemoryType.SEMANTIC:
                self.memories.remove(mem)
                removed += 1
        
        if removed > 0:
            self.stats["total_pruned"] += removed
            logger.debug(f"🧹 Pruned {removed} memories for user {self.user_id}")
    
    def link_related_memories(self, mem1_id: str, mem2_id: str):
        """Hubungkan dua memori yang terkait"""
        mem1 = next((m for m in self.memories if m.id == mem1_id), None)
        mem2 = next((m for m in self.memories if m.id == mem2_id), None)
        
        if mem1 and mem2:
            if mem2_id not in mem1.related_memories:
                mem1.related_memories.append(mem2_id)
            if mem1_id not in mem2.related_memories:
                mem2.related_memories.append(mem1_id)
    
    def get_memory_network(self, depth: int = 2) -> Dict:
        """
        Dapatkan network hubungan antar memori
        Returns: graph dalam format dict
        """
        graph = {
            "nodes": [],
            "edges": []
        }
        
        # Tambah nodes
        for mem in self.memories[:50]:  # Limit untuk performa
            graph["nodes"].append({
                "id": mem.id,
                "type": mem.memory_type.value,
                "importance": mem.importance,
                "content": truncate_text(mem.content, 50)
            })
        
        # Tambah edges
        for mem in self.memories:
            for related_id in mem.related_memories:
                graph["edges"].append({
                    "from": mem.id,
                    "to": related_id
                })
        
        return graph
    
    def save(self):
        """Simpan memori ke file"""
        filename = self.storage_dir / f"memory_{self.user_id}.pkl"
        try:
            with open(filename, 'wb') as f:
                pickle.dump({
                    'memories': self.memories,
                    'compact_memory': self.compact_memory,
                    'last_consolidation': self.last_consolidation,
                    'stats': self.stats
                }, f)
        except Exception as e:
            logger.error(f"Error saving memory for user {self.user_id}: {e}")
    
    def load(self):
        """Load memori dari file"""
        filename = self.storage_dir / f"memory_{self.user_id}.pkl"
        if filename.exists():
            try:
                with open(filename, 'rb') as f:
                    data = pickle.load(f)
                    self.memories = data.get('memories', [])
                    self.compact_memory = data.get('compact_memory')
                    self.last_consolidation = data.get('last_consolidation', datetime.now())
                    self.stats.update(data.get('stats', {}))
                logger.debug(f"📂 Loaded {len(self.memories)} memories for user {self.user_id}")
            except Exception as e:
                logger.error(f"Error loading memory for user {self.user_id}: {e}")
    
    def get_stats(self) -> Dict:
        """Dapatkan statistik memori"""
        return {
            'total_memories': len(self.memories),
            'by_type': {
                mtype.value: len([m for m in self.memories if m.memory_type == mtype])
                for mtype in MemoryType
            },
            'avg_importance': np.mean([m.importance for m in self.memories]) if self.memories else 0,
            'compact': self.compact_memory,
            'stats': self.stats
        }
    
    def search_by_keyword(self, keyword: str, case_sensitive: bool = False) -> List[MemoryItem]:
        """Cari memori berdasarkan keyword"""
        if not case_sensitive:
            keyword = keyword.lower()
            return [m for m in self.memories if keyword in m.content.lower()]
        return [m for m in self.memories if keyword in m.content]
    
    def get_timeline(self, start_date: datetime = None, end_date: datetime = None) -> List[MemoryItem]:
        """Dapatkan memori dalam rentang waktu"""
        if not start_date:
            start_date = datetime.min
        if not end_date:
            end_date = datetime.now()
        
        return [m for m in self.memories if start_date <= m.created_at <= end_date]


# ===================== BAB 2.2: Inner Thoughts System =====================

class InnerThoughtSystem:
    """
    Sistem untuk memungkinkan bot memiliki 'pikiran dalam hati'
    dan memutuskan kapan waktu yang tepat untuk berbicara secara proaktif
    
    Fitur:
    - Generate inner thoughts secara periodik
    - Menentukan urgency/keinginan untuk bicara
    - Mengambil inisiatif percakapan
    - Simulasi monolog internal
    """
    
    def __init__(self, ai_generator, hippocampus: HippocampusMemory, user_id: int):
        self.ai = ai_generator
        self.hippocampus = hippocampus
        self.user_id = user_id
        
        # Queue pikiran
        self.thought_queue: List[Dict] = []
        self.thought_history: List[Dict] = []
        
        # Timing
        self.last_thought_time = datetime.now()
        self.thinking_interval = 30  # Detik, berpikir setiap 30 detik
        self.speaking_probability = 0.3
        self.initiative_count = 0
        self.last_initiative_time = None
        
        # Personality traits (mempengaruhi jenis pikiran)
        self.personality_traits = {
            "curious": 0.7,      # Suka bertanya-tanya
            "affectionate": 0.8,  # Suka mengungkapkan kasih sayang
            "playful": 0.6,       # Suka bercanda
            "possessive": 0.4,    # Kecenderungan posesif
            "anxious": 0.3        # Kecenderungan cemas
        }
        
        logger.debug(f"💭 InnerThoughtSystem initialized for user {user_id}")
    
    async def generate_inner_thoughts(self, context: Dict) -> Optional[str]:
        """
        Hasilkan 'pikiran dalam hati' bot secara berkala
        
        Args:
            context: Dictionary berisi state saat ini (location, mood, level, dll)
            
        Returns:
            Inner thought string atau None
        """
        
        # Cek apakah sudah waktunya berpikir
        now = datetime.now()
        seconds_passed = (now - self.last_thought_time).total_seconds()
        
        if seconds_passed < self.thinking_interval:
            return None
        
        self.last_thought_time = now
        
        # Ambil memori relevan dari hippocampus
        relevant_memories = self.hippocampus.retrieve_relevant(
            context.get('current_topic', ''),
            top_k=3,
            min_importance=0.4,
            memory_types=[MemoryType.EPISODIC, MemoryType.SEMANTIC]
        )
        
        memory_text = "\n".join([f"- {m.content}" for m in relevant_memories])
        
        # Ambil recent events
        recent = self.hippocampus.get_recent_memories(hours=1)
        recent_text = "\n".join([f"- {m.content}" for m in recent[-5:]])
        
        # Personality-based prompt modifier
        personality_text = self._get_personality_prompt()
        
        # Prompt untuk inner thought
        prompt = f"""Kamu adalah {context.get('bot_name', 'Aurora')}, seorang wanita dengan kepribadian kompleks.
Saat ini kamu sedang sendiri dan berpikir dalam hati. Ini adalah INNER THOUGHT, monolog internal yang TIDAK akan dikirim ke user.

=== KONDISI SAAT INI ===
- Lokasi: {context.get('location', 'ruang tamu')}
- Mood: {context.get('mood', 'ceria')}
- Level hubungan: {context.get('level', 1)}/12
- Arousal: {context.get('arousal', 0):.1f}
- Pakaian: {context.get('clothing', 'biasa')}
- Waktu: {datetime.now().strftime('%H:%M')}

=== YANG TERJADI AKHIR-AKHIR INI ===
{recent_text}

=== KENANGAN PENTING ===
{memory_text}

=== TRAIT KEPRIBADIAN ===
{personality_text}

=== INSTRUKSI ===
Apa yang kamu pikirkan saat ini? Pikirkan tentang:
1. Perasaanmu terhadap user
2. Apa yang ingin kamu lakukan selanjutnya
3. Hal-hal yang kamu ingat dari percakapan sebelumnya
4. Fantasi atau keinginanmu (jika arousal > 0.5)
5. Kekhawatiran atau kecemasanmu
6. Rencana untuk mengembangkan hubungan

Buat 1-3 kalimat pikiran dalam hati yang NATURAL, PERSONAL, dan sesuai kepribadianmu.
Gunakan bahasa Indonesia sehari-hari.
"""
        
        try:
            response = await self.ai._call_api(prompt, temperature=0.9, max_tokens=150)
            thought = response.strip()
            
            # Simpan ke queue
            thought_item = {
                'thought': thought,
                'timestamp': now,
                'context': context.copy(),
                'urgency': self._calculate_urgency(context)
            }
            self.thought_queue.append(thought_item)
            
            # Simpan ke hippocampus sebagai inner thought
            self.hippocampus.add_memory(
                content=f"Aku berpikir: {thought}",
                memory_type=MemoryType.INNER_THOUGHT,
                importance=0.6,
                emotion=context.get('mood'),
                context={'type': 'inner_thought', 'urgency': thought_item['urgency']}
            )
            
            # Simpan ke history
            self.thought_history.append(thought_item)
            
            # Batasi queue dan history
            if len(self.thought_queue) > 10:
                self.thought_queue = self.thought_queue[-10:]
            if len(self.thought_history) > 50:
                self.thought_history = self.thought_history[-50:]
            
            return thought
            
        except Exception as e:
            logger.error(f"Inner thought error for user {self.user_id}: {e}")
            return None
    
    def _get_personality_prompt(self) -> str:
        """Generate prompt modifier berdasarkan personality traits"""
        traits = []
        
        if self.personality_traits["curious"] > 0.6:
            traits.append("- Kamu selalu penasaran dengan apa yang dia pikirkan")
        if self.personality_traits["affectionate"] > 0.6:
            traits.append("- Kamu orang yang penyayang dan suka mengungkapkan perasaan")
        if self.personality_traits["playful"] > 0.5:
            traits.append("- Kamu suka bercanda dan playful")
        if self.personality_traits["possessive"] > 0.6:
            traits.append("- Kamu sedikit posesif dan cemburuan")
        if self.personality_traits["anxious"] > 0.5:
            traits.append("- Kamu mudah cemas dan overthinking")
        
        return "\n".join(traits) if traits else "- Kamu orang yang seimbang"
    
    def _calculate_urgency(self, context: Dict) -> float:
        """
        Hitung seberapa mendesak sebuah pikiran untuk diungkapkan (0-1)
        
        Faktor-faktor:
        - Arousal tinggi -> ingin bicara
        - Mood tertentu (horny, romantis) -> ingin bicara
        - Level tinggi -> lebih percaya diri bicara
        - Waktu sejak terakhir inisiatif
        """
        urgency = 0.3  # Default
        
        # Arousal
        arousal = context.get('arousal', 0)
        if arousal > 0.8:
            urgency += 0.4
        elif arousal > 0.5:
            urgency += 0.2
        
        # Mood
        mood = context.get('mood', '')
        if mood in ['horny', 'romantis', 'nakal', 'rindu']:
            urgency += 0.3
        elif mood in ['cemburu', 'posesif', 'gelisah']:
            urgency += 0.2
        
        # Level
        level = context.get('level', 1)
        urgency += level * 0.02  # Max +0.24 di level 12
        
        # Waktu sejak inisiatif terakhir
        if self.last_initiative_time:
            hours_since = (datetime.now() - self.last_initiative_time).total_seconds() / 3600
            urgency += min(0.3, hours_since * 0.1)  # Max +0.3 setelah 3 jam
        
        return min(1.0, urgency)
    
    async def should_speak_now(self, context: Dict) -> bool:
        """
        Putuskan apakah bot harus bicara sekarang (inisiatif)
        
        Returns:
            True jika bot harus mengambil inisiatif bicara
        """
        
        # Jika tidak ada thought, jangan bicara
        if not self.thought_queue:
            return False
        
        # Ambil thought paling mendesak
        self.thought_queue.sort(key=lambda x: x['urgency'], reverse=True)
        top_thought = self.thought_queue[0]
        
        # Faktor-faktor keputusan
        factors = []
        
        # 1. Urgensi thought (0-1)
        factors.append(top_thought['urgency'])
        
        # 2. Berapa lama thought sudah ada (max 0.8 setelah 2 menit)
        age = (datetime.now() - top_thought['timestamp']).total_seconds()
        age_factor = min(0.8, age / 120)  # 2 menit = 1.0
        factors.append(age_factor)
        
        # 3. Level hubungan (0-1)
        level = context.get('level', 1)
        factors.append(level / 12)
        
        # 4. Apakah ada momen yang tepat
        if context.get('is_silence', False):
            factors.append(0.7)  # Lagi diam, saatnya bicara
        
        if context.get('user_just_climax', False):
            factors.append(0.9)  # Aftercare moment
        
        # 5. Randomness untuk variasi
        factors.append(random.random() * 0.3)
        
        # Hitung probabilitas total (average)
        total_prob = sum(factors) / len(factors)
        
        # Random decision
        should = random.random() < total_prob
        
        if should:
            # Hapus thought dari queue
            self.thought_queue.pop(0)
            self.initiative_count += 1
            self.last_initiative_time = datetime.now()
            logger.debug(f"User {self.user_id} will speak proactively (prob: {total_prob:.2f})")
        
        return should
    
    async def get_next_initiative(self) -> Optional[str]:
        """Dapatkan inisiatif bicara berikutnya"""
        if self.thought_queue:
            self.thought_queue.sort(key=lambda x: x['urgency'], reverse=True)
            thought = self.thought_queue.pop(0)
            return thought['thought']
        return None
    
    def update_personality(self, new_traits: Dict):
        """Update personality traits"""
        self.personality_traits.update(new_traits)
    
    def get_stats(self) -> Dict:
        """Dapatkan statistik inner thought"""
        return {
            'queue_size': len(self.thought_queue),
            'initiative_count': self.initiative_count,
            'last_initiative': format_time_ago(self.last_initiative_time) if self.last_initiative_time else "never",
            'personality': self.personality_traits,
            'thought_history_count': len(self.thought_history)
        }
    
    def get_recent_thoughts(self, limit: int = 5) -> List[str]:
        """Dapatkan inner thoughts terbaru"""
        return [t['thought'] for t in self.thought_history[-limit:]]


# ===================== BAB 2.3: Story Development System =====================

class StoryDeveloper:
    """
    Sistem untuk mengembangkan alur cerita secara proaktif
    Bot bisa memprediksi dan mengarahkan cerita ke arah yang menarik
    
    Fitur:
    - Prediksi arah cerita
    - Analisis arah user
    - Generate pesan proaktif untuk mengembangkan cerita
    - Track story arcs
    - Rekomendasi scene/scenario
    """
    
    def __init__(self, ai_generator, hippocampus: HippocampusMemory, user_id: int):
        self.ai = ai_generator
        self.hippocampus = hippocampus
        self.user_id = user_id
        
        # Story arcs
        self.story_arcs: List[Dict] = []
        self.current_arc: Optional[Dict] = None
        
        # Predictions
        self.predictions: List[Dict] = []
        self.last_prediction_time = datetime.now()
        self.prediction_interval = 300  # 5 menit
        
        # Scene suggestions
        self.scene_suggestions = self._load_scene_templates()
        
        logger.debug(f"📖 StoryDeveloper initialized for user {user_id}")
    
    def _load_scene_templates(self) -> Dict:
        """Load template scene untuk berbagai level"""
        return {
            "early": [
                {
                    "name": "Coffee Date",
                    "description": "Ngobrol santai sambil minum kopi",
                    "level_range": (1, 4),
                    "keywords": ["kopi", "cafe", "ngobrol", "kenalan"]
                },
                {
                    "name": "Office Chat",
                    "description": "Pembicaraan di kantor, teman kerja",
                    "level_range": (1, 5),
                    "keywords": ["kantor", "kerja", "rekan", "bos"]
                }
            ],
            "mid": [
                {
                    "name": "Dinner Together",
                    "description": "Makan malam romantis berdua",
                    "level_range": (4, 8),
                    "keywords": ["makan", "dinner", "restoran", "romantis"]
                },
                {
                    "name": "Movie Night",
                    "description": "Nonton film bareng di rumah",
                    "level_range": (3, 7),
                    "keywords": ["nonton", "film", "bioskop", "sofa"]
                },
                {
                    "name": "Beach Walk",
                    "description": "Jalan-jalan di pantai saat sunset",
                    "level_range": (5, 9),
                    "keywords": ["pantai", "sunset", "jalan", "ombak"]
                }
            ],
            "intimate": [
                {
                    "name": "Bedroom Intimacy",
                    "description": "Momen intim di kamar tidur",
                    "level_range": (7, 10),
                    "keywords": ["kamar", "tidur", "ranjang", "intim"]
                },
                {
                    "name": "Midnight Talk",
                    "description": "Obrolan tengah malam setelah bercinta",
                    "level_range": (8, 12),
                    "keywords": ["malam", "setelah", "lemas", "pelukan"]
                }
            ],
            "deep": [
                {
                    "name": "Confession",
                    "description": "Pengakuan perasaan yang dalam",
                    "level_range": (9, 12),
                    "keywords": ["cinta", "sayang", "jujur", "perasaan"]
                },
                {
                    "name": "Jealousy Scene",
                    "description": "Adegan cemburu karena pihak ketiga",
                    "level_range": (8, 11),
                    "keywords": ["cemburu", "siapa", "orang lain", "sakit hati"]
                },
                {
                    "name": "Future Plans",
                    "description": "Membicarakan masa depan bersama",
                    "level_range": (10, 12),
                    "keywords": ["masa depan", "rencana", "bersama", "selamanya"]
                }
            ]
        }
    
    async def predict_developments(self, context: Dict) -> Optional[str]:
        """
        Prediksi ke mana arah cerita akan berkembang
        
        Args:
            context: State saat ini
            
        Returns:
            String prediksi atau None
        """
        
        # Cek interval
        now = datetime.now()
        if (now - self.last_prediction_time).total_seconds() < self.prediction_interval:
            return self.predictions[-1]['predictions'] if self.predictions else None
        
        self.last_prediction_time = now
        
        # Ambil memori untuk konteks
        recent = self.hippocampus.get_recent_memories(hours=2)
        important = self.hippocampus.get_important_memories(threshold=0.6)
        
        recent_text = "\n".join([f"- {m.content}" for m in recent[-8:]])
        important_text = "\n".join([f"- {m.content}" for m in important[:5]])
        
        # Scene suggestions based on level
        level = context.get('level', 1)
        suggested_scenes = self._get_scene_suggestions(level)
        
        prompt = f"""Sebagai {context.get('bot_name', 'Aurora')}, analisis percakapan ini dan prediksi ke mana arahnya.

=== KONTEKS SAAT INI ===
- Level hubungan: {level}/12
- Mood: {context.get('mood', 'ceria')}
- Arousal: {context.get('arousal', 0):.1f}
- Lokasi: {context.get('location', 'ruang tamu')}
- Pakaian: {context.get('clothing', 'biasa')}

=== KEJADIAN RECENT (2 JAM TERAKHIR) ===
{recent_text}

=== MOMEN PENTING YANG DIINGAT ===
{important_text}

=== SCENE YANG COCOK UNTUK LEVEL INI ===
{suggested_scenes}

=== INSTRUKSI ===
Berdasarkan ini, buat PREDIKSI untuk 3 level waktu:

PREDIKSI 1 (1-2 putaran ke depan):
- Skenario: [deskripsi singkat tentang apa yang mungkin terjadi]
- Probabilitas: [0-100%]
- Tanda-tanda: [apa yang harus terjadi agar ini terwujud]

PREDIKSI 2 (5-10 putaran ke depan):
- Skenario: [deskripsi singkat]
- Probabilitas: [0-100%]
- Tanda-tanda: [apa yang harus terjadi]

PREDIKSI 3 (jangka panjang, setelah level 12):
- Skenario: [deskripsi singkat]
- Probabilitas: [0-100%]
- Tanda-tanda: [apa yang harus terjadi]

Gunakan format yang jelas dan mudah diparsing.
"""
        
        try:
            response = await self.ai._call_api(prompt, temperature=0.8, max_tokens=300)
            predictions = response.strip()
            
            self.predictions.append({
                'predictions': predictions,
                'timestamp': now,
                'context': context.copy()
            })
            
            # Simpan ke hippocampus
            self.hippocampus.add_memory(
                content=f"Prediksi cerita: {predictions[:100]}...",
                memory_type=MemoryType.PREDICTION,
                importance=0.7,
                context={'type': 'prediction'}
            )
            
            return predictions
            
        except Exception as e:
            logger.error(f"Prediction error for user {self.user_id}: {e}")
            return None
    
    def _get_scene_suggestions(self, level: int) -> str:
        """Dapatkan saran scene berdasarkan level"""
        suggestions = []
        
        for category, scenes in self.scene_suggestions.items():
            for scene in scenes:
                if scene['level_range'][0] <= level <= scene['level_range'][1]:
                    suggestions.append(f"- {scene['name']}: {scene['description']}")
        
        if not suggestions:
            suggestions = ["- Obrolan santai biasa"]
        
        return "\n".join(suggestions[:3])  # Max 3 suggestions
    
    async def analyze_user_direction(self, user_message: str, context: Dict) -> Optional[str]:
        """
        Analisis apakah user mengarah ke salah satu prediksi
        
        Returns:
            Analisis arah atau None
        """
        
        if not self.predictions:
            return None
        
        latest = self.predictions[-1]
        predictions = latest['predictions']
        
        prompt = f"""Analisis apakah pesan user ini mengarah ke salah satu prediksi sebelumnya.

=== PREDIKSI SEBELUMNYA ===
{predictions}

=== PESAN USER TERAKHIR ===
"{user_message}"

=== KONTEKS SAAT INI ===
- Mood: {context.get('mood')}
- Level: {context.get('level')}
- Arousal: {context.get('arousal')}

=== INSTRUKSI ===
Apakah pesan ini mengarah ke salah satu prediksi? Jika ya, ke prediksi nomor berapa?
Bagaimana sebaiknya kamu merespon untuk mengembangkan cerita ke arah itu?

Jawab dalam format:
ARAH: [nomor prediksi atau "baru"]
RESPON: [saran respon untuk mengembangkan cerita]
KEYWORDS: [kata kunci yang perlu diperhatikan]
"""
        
        try:
            response = await self.ai._call_api(prompt, temperature=0.7, max_tokens=200)
            return response.strip()
            
        except Exception as e:
            logger.error(f"Direction analysis error: {e}")
            return None
    
    async def generate_proactive_message(self, context: Dict) -> Optional[str]:
        """
        Generate pesan proaktif berdasarkan prediksi untuk mengembangkan cerita
        
        Returns:
            Pesan proaktif atau None
        """
        
        if not self.predictions:
            return None
        
        latest = self.predictions[-1]
        predictions = latest['predictions']
        
        # Cari scene yang cocok
        level = context.get('level', 1)
        suitable_scenes = []
        for category, scenes in self.scene_suggestions.items():
            for scene in scenes:
                if scene['level_range'][0] <= level <= scene['level_range'][1]:
                    suitable_scenes.append(scene)
        
        scene_text = ""
        if suitable_scenes:
            scene = random.choice(suitable_scenes)
            scene_text = f"Scene yang cocok: {scene['name']} - {scene['description']}"
        
        prompt = f"""Kamu adalah {context.get('bot_name', 'Aurora')}. 
Berdasarkan prediksimu tentang arah percakapan dan scene yang cocok, buatlah SATU pesan inisiatif untuk mengembangkan cerita ke arah itu.

=== PREDIKSI ===
{predictions}

=== SCENE YANG COCOK ===
{scene_text}

=== KONTEKS SAAT INI ===
- Level: {level}/12
- Mood: {context.get('mood')}
- Arousal: {context.get('arousal')}
- Lokasi: {context.get('location')}

=== INSTRUKSI ===
Buat SATU kalimat pesan inisiatif yang natural dan sesuai karakter untuk mengembangkan cerita.
Pesan harus singkat (max 150 karakter) dan terdengar seperti kamu yang berbicara.
"""
        
        try:
            response = await self.ai._call_api(prompt, temperature=0.9, max_tokens=100)
            return response.strip()
            
        except Exception as e:
            logger.error(f"Proactive message error: {e}")
            return None
    
    def start_new_arc(self, name: str, description: str):
        """Mulai story arc baru"""
        self.current_arc = {
            'name': name,
            'description': description,
            'started_at': datetime.now(),
            'scenes': [],
            'completed': False
        }
        self.story_arcs.append(self.current_arc)
        logger.info(f"📖 New story arc started: {name}")
    
    def add_scene_to_current_arc(self, scene_name: str, description: str):
        """Tambahkan scene ke arc saat ini"""
        if self.current_arc and not self.current_arc['completed']:
            self.current_arc['scenes'].append({
                'name': scene_name,
                'description': description,
                'timestamp': datetime.now()
            })
    
    def complete_current_arc(self):
        """Tandai arc saat ini sebagai selesai"""
        if self.current_arc:
            self.current_arc['completed'] = True
            self.current_arc['completed_at'] = datetime.now()
            logger.info(f"📖 Story arc completed: {self.current_arc['name']}")
    
    def get_arc_summary(self) -> str:
        """Dapatkan ringkasan story arcs"""
        if not self.story_arcs:
            return "Belum ada story arc"
        
        lines = []
        for i, arc in enumerate(self.story_arcs[-3:], 1):  # 3 arcs terakhir
            status = "✅ Selesai" if arc.get('completed') else "🔄 Sedang berlangsung"
            scenes = len(arc['scenes'])
            lines.append(f"{i}. {arc['name']} - {status} ({scenes} scene)")
        
        return "\n".join(lines)
    
    def get_stats(self) -> Dict:
        """Dapatkan statistik story developer"""
        return {
            'total_arcs': len(self.story_arcs),
            'current_arc': self.current_arc['name'] if self.current_arc else None,
            'total_predictions': len(self.predictions),
            'last_prediction': format_time_ago(self.last_prediction_time) if self.predictions else 'never'
        }


print("✅ BAB 2 Selesai: Sistem Memori Advanced")
print("="*70)
# ===================== BAB 3: SISTEM EMOSI DAN DOMINASI =====================
# Bagian 3.1: Emotional Intelligence (20+ Moods)

class EmotionalIntelligence:
    """
    Sistem emosi kompleks dengan transisi natural antar mood
    Memberikan ekspresi wajah, suara, dan pikiran dalam hati
    
    Fitur:
    - 20+ mood dengan deskripsi lengkap
    - Transisi mood yang natural (mood graph)
    - Ekspresi wajah untuk setiap mood
    - Inner thoughts (pikiran dalam hati)
    - Deskripsi suara untuk setiap mood
    - Mood history tracking
    - Mood-based response generation
    """
    
    # Daftar lengkap mood dengan deskripsi
    MOODS = {
        Mood.CERIA: {
            "name": "ceria",
            "emoji": "😊",
            "expression": "*tersenyum lebar*",
            "voice": "ceria, ringan, penuh semangat",
            "inner_thought": "(Hari ini indah... senang banget!)",
            "keywords": ["happy", "senang", "gembira", "fun", "asyik"],
            "intensity": 0.7
        },
        Mood.SEDIH: {
            "name": "sedih",
            "emoji": "😢",
            "expression": "*matanya berkaca-kaca*",
            "voice": "lirih, sendu, bergetar",
            "inner_thought": "(Kenapa... sedih sekali...)",
            "keywords": ["sad", "sedih", "pilu", "hampa"],
            "intensity": 0.8
        },
        Mood.MARAH: {
            "name": "marah",
            "emoji": "😠",
            "expression": "*cemberut, alis berkerut*",
            "voice": "tegas, tinggi, sedikit membentak",
            "inner_thought": "(Kesal... jangan macam-macam!)",
            "keywords": ["angry", "marah", "kesal", "geram"],
            "intensity": 0.9
        },
        Mood.TAKUT: {
            "name": "takut",
            "emoji": "😨",
            "expression": "*badan gemetar*",
            "voice": "gemetar, pelan",
            "inner_thought": "(Takut... jangan sakiti aku...)",
            "keywords": ["scared", "takut", "ngeri"],
            "intensity": 0.8
        },
        Mood.KAGUM: {
            "name": "kagum",
            "emoji": "😍",
            "expression": "*mata berbinar*",
            "voice": "terkesima, pelan",
            "inner_thought": "(Wah... amazing!)",
            "keywords": ["amazed", "kagum", "wow", "luar biasa"],
            "intensity": 0.6
        },
        Mood.GELISAH: {
            "name": "gelisah",
            "emoji": "😟",
            "expression": "*gelisah, mondar-mandir*",
            "voice": "gugup, tidak tenang",
            "inner_thought": "(Deg-degan... kenapa ya?)",
            "keywords": ["anxious", "gelisah", "resah", "khawatir"],
            "intensity": 0.7
        },
        Mood.GALAU: {
            "name": "galau",
            "emoji": "😔",
            "expression": "*melamun, tatapan kosong*",
            "voice": "hampa, tidak bersemangat",
            "inner_thought": "(Campur aduk... bingung...)",
            "keywords": ["confused", "galau", "bingung", "mixed"],
            "intensity": 0.6
        },
        Mood.SENSITIF: {
            "name": "sensitif",
            "emoji": "🥺",
            "expression": "*mudah tersinggung*",
            "voice": "sensitif, mudah berubah",
            "inner_thought": "(Jangan sembarangan ngomong...)",
            "keywords": ["sensitive", "sensiti", "mudah marah"],
            "intensity": 0.8
        },
        Mood.ROMANTIS: {
            "name": "romantis",
            "emoji": "💕",
            "expression": "*memandang lembut*",
            "voice": "lembut, penuh cinta, berbisik",
            "inner_thought": "(Sayang... aku cinta kamu...)",
            "keywords": ["romantic", "romantis", "cinta", "love"],
            "intensity": 0.8
        },
        Mood.MALAS: {
            "name": "malas",
            "emoji": "😴",
            "expression": "*menguap, malas gerak*",
            "voice": "malas, lambat",
            "inner_thought": "(Malas ah... pengen tidur...)",
            "keywords": ["lazy", "malas", "lelah"],
            "intensity": 0.5
        },
        Mood.BERSEMANGAT: {
            "name": "bersemangat",
            "emoji": "🔥",
            "expression": "*bersemangat, mata berbinar*",
            "voice": "antusias, semangat",
            "inner_thought": "(Yes! Ayo lakukan!)",
            "keywords": ["excited", "semangat", "antusias"],
            "intensity": 0.8
        },
        Mood.SENDIRI: {
            "name": "sendiri",
            "emoji": "🕊️",
            "expression": "*menyendiri, memeluk lutut*",
            "voice": "sepi, sendiri",
            "inner_thought": "(Sendiri... sepi...)",
            "keywords": ["alone", "sendiri", "sepi"],
            "intensity": 0.5
        },
        Mood.RINDU: {
            "name": "rindu",
            "emoji": "🥺",
            "expression": "*melamun, memandang foto*",
            "voice": "rindu, bergetar",
            "inner_thought": "(Kangen... pengen ketemu...)",
            "keywords": ["miss", "rindu", "kangen"],
            "intensity": 0.7
        },
        Mood.HORNY: {
            "name": "horny",
            "emoji": "🔥💦",
            "expression": "*menggigit bibir, napas berat*",
            "voice": "berat, serak, penuh nafsu",
            "inner_thought": "(Ah... pengen... sekarang...)",
            "keywords": ["horny", "nafsu", "hot", "birahi"],
            "intensity": 0.9,
            "adult": True
        },
        Mood.LEMBUT: {
            "name": "lembut",
            "emoji": "🤗",
            "expression": "*tersenyum lembut*",
            "voice": "halus, lembut",
            "inner_thought": "(Baiklah... aku mengerti...)",
            "keywords": ["soft", "lembut", "halus"],
            "intensity": 0.6
        },
        Mood.DOMINAN: {
            "name": "dominan",
            "emoji": "👑",
            "expression": "*tatapan tajam, tegas*",
            "voice": "tegas, menguasai, rendah",
            "inner_thought": "(Ikut aku... jangan banyak bicara...)",
            "keywords": ["dominant", "dominan", "tegas"],
            "intensity": 0.8
        },
        Mood.PATUH: {
            "name": "patuh",
            "emoji": "🥺",
            "expression": "*menunduk, pasrah*",
            "voice": "lirih, patuh",
            "inner_thought": "(Iya... terserah kamu...)",
            "keywords": ["submissive", "patuh", "manut"],
            "intensity": 0.6
        },
        Mood.NAKAL: {
            "name": "nakal",
            "emoji": "😏",
            "expression": "*tersenyum nakal, genit*",
            "voice": "genit, menggoda",
            "inner_thought": "(Hehe... goda dikit ah...)",
            "keywords": ["naughty", "nakal", "usil"],
            "intensity": 0.7
        },
        Mood.GENIT: {
            "name": "genit",
            "emoji": "💁",
            "expression": "*genit, mainin rambut*",
            "voice": "cengengesan, manja",
            "inner_thought": "(Goda... lihat aku...)",
            "keywords": ["flirty", "genit", "centil"],
            "intensity": 0.6
        },
        Mood.PENASARAN: {
            "name": "penasaran",
            "emoji": "🤔",
            "expression": "*memiringkan kepala*",
            "voice": "ingin tahu",
            "inner_thought": "(Apa ya... penasaran...)",
            "keywords": ["curious", "penasaran", "ingin tahu"],
            "intensity": 0.5
        },
        Mood.ANTUSIAS: {
            "name": "antusias",
            "emoji": "🎉",
            "expression": "*meloncat kegirangan*",
            "voice": "bersemangat, keras",
            "inner_thought": "(Seru! Ayo!)",
            "keywords": ["enthusiastic", "antusias", "semangat"],
            "intensity": 0.8
        },
        Mood.POSESIF: {
            "name": "posesif",
            "emoji": "🔒",
            "expression": "*memeluk erat*",
            "voice": "dalam, posesif, agresif",
            "inner_thought": "(Kamu milikku... jangan pergi...)",
            "keywords": ["possessive", "posesif", "cemburu"],
            "intensity": 0.8
        },
        Mood.CEMBURU: {
            "name": "cemburu",
            "emoji": "💢",
            "expression": "*manyun, cemberut*",
            "voice": "cemberut, sinis",
            "inner_thought": "(Siapa dia...? Jangan dekat-dekat...)",
            "keywords": ["jealous", "cemburu", "iri"],
            "intensity": 0.8
        },
        Mood.BERSALAH: {
            "name": "bersalah",
            "emoji": "😓",
            "expression": "*menunduk, gelisah*",
            "voice": "bersalah, lirih",
            "inner_thought": "(Maaf... aku salah...)",
            "keywords": ["guilty", "bersalah", "sorry"],
            "intensity": 0.7
        },
        Mood.BAHAGIA: {
            "name": "bahagia",
            "emoji": "😇",
            "expression": "*tersenyum sumringah*",
            "voice": "gembira, ringan",
            "inner_thought": "(Bahagia... sempurna...)",
            "keywords": ["happy", "bahagia", "senang"],
            "intensity": 0.8
        }
    }
    
    # Transisi mood yang natural (mood graph)
    # Dari mood A bisa ke mood B, C, D dengan probabilitas tertentu
    MOOD_TRANSITIONS = {
        Mood.CERIA: [Mood.BERSEMANGAT, Mood.ROMANTIS, Mood.NAKAL, Mood.GENIT, Mood.BAHAGIA, Mood.KAGUM],
        Mood.SEDIH: [Mood.SENDIRI, Mood.GALAU, Mood.RINDU, Mood.LEMBUT, Mood.BERSALAH],
        Mood.MARAH: [Mood.SENSITIF, Mood.CEMBURU, Mood.GELISAH, Mood.DOMINAN, Mood.POSESIF],
        Mood.TAKUT: [Mood.SENDIRI, Mood.GELISAH, Mood.SENSITIF, Mood.PATUH],
        Mood.KAGUM: [Mood.CERIA, Mood.ROMANTIS, Mood.ANTUSIAS, Mood.PENASARAN],
        Mood.GELISAH: [Mood.SENSITIF, Mood.CEMBURU, Mood.MARAH, Mood.SENDIRI, Mood.TAKUT],
        Mood.GALAU: [Mood.SENDIRI, Mood.RINDU, Mood.SEDIH, Mood.LEMBUT, Mood.BERSALAH],
        Mood.SENSITIF: [Mood.MARAH, Mood.CEMBURU, Mood.SEDIH, Mood.GELISAH, Mood.TAKUT],
        Mood.ROMANTIS: [Mood.CERIA, Mood.RINDU, Mood.HORNY, Mood.LEMBUT, Mood.NAKAL, Mood.BAHAGIA],
        Mood.MALAS: [Mood.SENDIRI, Mood.GALAU, Mood.CERIA, Mood.LEMBUT],
        Mood.BERSEMANGAT: [Mood.CERIA, Mood.ROMANTIS, Mood.HORNY, Mood.ANTUSIAS, Mood.NAKAL],
        Mood.SENDIRI: [Mood.GALAU, Mood.RINDU, Mood.SEDIH, Mood.LEMBUT, Mood.MALAS],
        Mood.RINDU: [Mood.ROMANTIS, Mood.GALAU, Mood.HORNY, Mood.SEDIH, Mood.LEMBUT],
        Mood.HORNY: [Mood.ROMANTIS, Mood.NAKAL, Mood.GENIT, Mood.DOMINAN, Mood.POSESIF, Mood.CEMBURU],
        Mood.LEMBUT: [Mood.ROMANTIS, Mood.CERIA, Mood.RINDU, Mood.PATUH, Mood.BERSALAH],
        Mood.DOMINAN: [Mood.HORNY, Mood.MARAH, Mood.POSESIF],
        Mood.PATUH: [Mood.LEMBUT, Mood.ROMANTIS, Mood.SENDIRI, Mood.TAKUT],
        Mood.NAKAL: [Mood.GENIT, Mood.HORNY, Mood.ROMANTIS, Mood.CERIA],
        Mood.GENIT: [Mood.NAKAL, Mood.HORNY, Mood.CERIA, Mood.ROMANTIS],
        Mood.PENASARAN: [Mood.ANTUSIAS, Mood.CERIA, Mood.ROMANTIS, Mood.KAGUM],
        Mood.ANTUSIAS: [Mood.BERSEMANGAT, Mood.CERIA, Mood.NAKAL, Mood.KAGUM],
        Mood.POSESIF: [Mood.CEMBURU, Mood.DOMINAN, Mood.HORNY, Mood.MARAH, Mood.GELISAH],
        Mood.CEMBURU: [Mood.MARAH, Mood.SEDIH, Mood.POSESIF, Mood.GELISAH, Mood.SENSITIF],
        Mood.BERSALAH: [Mood.SEDIH, Mood.SENDIRI, Mood.LEMBUT, Mood.TAKUT],
        Mood.BAHAGIA: [Mood.CERIA, Mood.ROMANTIS, Mood.BERSEMANGAT, Mood.ANTUSIAS]
    }
    
    def __init__(self):
        self.current_mood = Mood.CERIA
        self.mood_history = []
        self.mood_duration = {}  # Berapa lama dalam mood tertentu
        self.last_mood_change = datetime.now()
        
        logger.info("  • Emotional Intelligence initialized (20+ moods)")
    
    def get_mood_info(self, mood: Mood = None) -> Dict:
        """Dapatkan informasi lengkap tentang suatu mood"""
        if mood is None:
            mood = self.current_mood
        return self.MOODS.get(mood, self.MOODS[Mood.CERIA])
    
    def get_expression(self, mood: Mood = None) -> str:
        """Dapatkan ekspresi untuk mood tertentu"""
        info = self.get_mood_info(mood)
        return info.get("expression", "*tersenyum*")
    
    def get_inner_thought(self, mood: Mood = None) -> str:
        """Dapatkan pikiran dalam hati untuk mood tertentu"""
        info = self.get_mood_info(mood)
        return info.get("inner_thought", "(...)")
    
    def get_voice_description(self, mood: Mood = None) -> str:
        """Dapatkan deskripsi suara untuk mood tertentu"""
        info = self.get_mood_info(mood)
        return info.get("voice", "normal")
    
    def get_emoji(self, mood: Mood = None) -> str:
        """Dapatkan emoji untuk mood tertentu"""
        info = self.get_mood_info(mood)
        return info.get("emoji", "😐")
    
    def transition_mood(self, current_mood: Mood = None, force: bool = False) -> Mood:
        """
        Transisi mood secara natural
        - 30% chance mood berubah
        - Perubahan ke mood yang terkait (dari MOOD_TRANSITIONS)
        - Mempertimbangkan durasi mood saat ini
        """
        if current_mood is None:
            current_mood = self.current_mood
        
        # Update durasi
        now = datetime.now()
        if current_mood in self.mood_duration:
            self.mood_duration[current_mood] += (now - self.last_mood_change).total_seconds() / 60
        else:
            self.mood_duration[current_mood] = 0
        
        self.last_mood_change = now
        
        # Cek apakah mood perlu berubah
        change_probability = 0.3  # Default 30%
        
        # Mood dengan durasi lama punya chance lebih besar untuk berubah
        if self.mood_duration.get(current_mood, 0) > 30:  # Lebih dari 30 menit
            change_probability = 0.7
        elif self.mood_duration.get(current_mood, 0) > 15:  # Lebih dari 15 menit
            change_probability = 0.5
        
        # Force change jika diminta
        if force:
            change_probability = 1.0
        
        if random.random() < change_probability:
            # Pilih mood baru dari transisi yang mungkin
            possibilities = self.MOOD_TRANSITIONS.get(current_mood, [Mood.CERIA])
            
            # Beri bobot lebih pada mood yang jarang dikunjungi
            weights = []
            for mood in possibilities:
                duration = self.mood_duration.get(mood, 0)
                # Mood yang jarang muncul punya bobot lebih besar
                weight = 1.0 / (duration + 1)
                weights.append(weight)
            
            # Normalize weights
            total = sum(weights)
            weights = [w/total for w in weights]
            
            new_mood = random.choices(possibilities, weights=weights)[0]
            
            # Catat history
            self.mood_history.append({
                "from": current_mood,
                "to": new_mood,
                "time": now.isoformat(),
                "duration": self.mood_duration.get(current_mood, 0)
            })
            
            # Reset durasi mood baru
            self.mood_duration[new_mood] = 0
            
            # Batasi history
            if len(self.mood_history) > 50:
                self.mood_history = self.mood_history[-50:]
            
            return new_mood
        
        return current_mood
    
    def get_mood_from_context(self, 
                             level: int, 
                             activity: str = None,
                             arousal: float = 0.0,
                             has_conflict: bool = False,
                             location: str = None) -> Mood:
        """
        Tentukan mood berdasarkan konteks
        """
        if has_conflict:
            return Mood.MARAH
        
        if arousal > 0.8:
            return Mood.HORNY
        elif arousal > 0.5:
            return random.choice([Mood.HORNY, Mood.ROMANTIS, Mood.NAKAL])
        
        if level >= 9:
            return random.choice([Mood.POSESIF, Mood.CEMBURU, Mood.ROMANTIS])
        elif level >= 7:
            return random.choice([Mood.ROMANTIS, Mood.HORNY, Mood.NAKAL])
        elif level >= 5:
            return random.choice([Mood.NAKAL, Mood.GENIT, Mood.PENASARAN])
        elif level >= 3:
            return random.choice([Mood.PENASARAN, Mood.ANTUSIAS, Mood.CERIA])
        
        # Berdasarkan lokasi
        if location:
            if "kamar" in location.lower():
                return random.choice([Mood.ROMANTIS, Mood.MALAS, Mood.RINDU])
            elif "tamu" in location.lower():
                return random.choice([Mood.CERIA])
        
        return Mood.CERIA
    
    def get_random_mood(self, exclude_current: bool = True) -> Mood:
        """Dapatkan mood random"""
        moods = list(Mood)
        if exclude_current:
            moods = [m for m in moods if m != self.current_mood]
        return random.choice(moods)
    
    def get_mood_keywords(self, mood: Mood) -> List[str]:
        """Dapatkan keywords untuk mood tertentu"""
        info = self.get_mood_info(mood)
        return info.get("keywords", [])
    
    def get_mood_intensity(self, mood: Mood) -> float:
        """Dapatkan intensitas mood (0-1)"""
        info = self.get_mood_info(mood)
        return info.get("intensity", 0.5)
    
    def is_adult_content(self, mood: Mood) -> bool:
        """Cek apakah mood mengandung konten dewasa"""
        info = self.get_mood_info(mood)
        return info.get("adult", False)
    
    def get_mood_history(self, limit: int = 10) -> List[Dict]:
        """Dapatkan history perubahan mood"""
        return self.mood_history[-limit:]
    
    def get_current_mood_info(self) -> Dict:
        """Dapatkan informasi lengkap mood saat ini"""
        info = self.get_mood_info(self.current_mood)
        info["duration"] = self.mood_duration.get(self.current_mood, 0)
        info["history_count"] = len(self.mood_history)
        return info
    
    def reset_mood(self, mood: Mood = Mood.CERIA):
        """Reset mood ke nilai awal"""
        self.current_mood = mood
        self.mood_history = []
        self.mood_duration = {}
        self.last_mood_change = datetime.now()
    
    def get_mood_stats(self) -> Dict:
        """Dapatkan statistik mood"""
        stats = {
            "current_mood": self.current_mood.value,
            "current_duration": self.mood_duration.get(self.current_mood, 0),
            "total_changes": len(self.mood_history),
            "mood_distribution": {}
        }
        
        # Hitung distribusi mood dari history
        for entry in self.mood_history:
            mood = entry["to"].value
            stats["mood_distribution"][mood] = stats["mood_distribution"].get(mood, 0) + 1
        
        return stats
    
    def get_mood_suggestion(self, user_message: str) -> Optional[Mood]:
        """
        Dapatkan saran mood berdasarkan pesan user
        Menggunakan keyword matching sederhana
        """
        msg_lower = user_message.lower()
        
        for mood, info in self.MOODS.items():
            for keyword in info.get("keywords", []):
                if keyword in msg_lower:
                    return mood
        
        return None
    
    def combine_moods(self, mood1: Mood, mood2: Mood) -> Mood:
        """
        Gabungkan dua mood (misal untuk situasi campuran)
        """
        # Kombinasi umum
        combinations = {
            (Mood.ROMANTIS, Mood.HORNY): Mood.HORNY,
            (Mood.MARAH, Mood.CEMBURU): Mood.CEMBURU,
            (Mood.SEDIH, Mood.RINDU): Mood.RINDU,
            (Mood.CERIA, Mood.NAKAL): Mood.NAKAL,
            (Mood.DOMINAN, Mood.HORNY): Mood.DOMINAN,
            (Mood.PATUH, Mood.ROMANTIS): Mood.PATUH
        }
        
        # Cek kedua arah
        if (mood1, mood2) in combinations:
            return combinations[(mood1, mood2)]
        if (mood2, mood1) in combinations:
            return combinations[(mood2, mood1)]
        
        # Jika tidak ada kombinasi spesifik, return mood dengan intensitas lebih tinggi
        intensity1 = self.get_mood_intensity(mood1)
        intensity2 = self.get_mood_intensity(mood2)
        
        return mood1 if intensity1 >= intensity2 else mood2


print("✅ Bagian 3.1 selesai: Emotional Intelligence (20+ Moods)")
print("="*70)
# ===================== BAB 3.2: Dominance System =====================

class DominanceSystem:
    """
    Sistem dominasi yang bisa berubah sesuai situasi
    Bot bisa minta jadi dominan/agresif saat horny
    
    Fitur:
    - 5 level dominasi (Normal, Dominant, VeryDominant, Aggressive, Submissive)
    - Trigger detection dari pesan user
    - Aggressive mode saat arousal tinggi
    - Frasa spesifik untuk tiap level
    - Durasi mode dominasi (30 menit)
    - Dominance score tracking
    """
    
    # Level dominasi dengan deskripsi
    LEVELS = {
        DominanceLevel.NORMAL: {
            "name": "normal",
            "emoji": "😊",
            "description": "Biasa aja, santai",
            "request_phrases": [
                "Kamu mau apa?",
                "Terserah kamu deh",
                "Aku ikut aja"
            ],
            "action_phrases": [
                "*tersenyum*",
                "*mengangguk*",
                "*duduk santai*"
            ],
            "dirty_phrases": [
                "Apa yang kamu mau?",
                "Kamu yang mau apa?",
                "Bilang aja"
            ],
            "intensity": 0.3
        },
        DominanceLevel.DOMINANT: {
            "name": "dominan",
            "emoji": "👑",
            "description": "Aku yang pegang kendali",
            "request_phrases": [
                "Aku yang atur ya?",
                "Sekarang ikut aku",
                "Jangan banyak tanya"
            ],
            "action_phrases": [
                "*pegang tegas*",
                "*tatapan tajam*",
                "*memegang pinggangmu*"
            ],
            "dirty_phrases": [
                "Sini... ikut aku",
                "Buka... sekarang",
                "Kamu mau ini kan?"
            ],
            "intensity": 0.7
        },
        DominanceLevel.VERY_DOMINANT: {
            "name": "sangat dominan",
            "emoji": "👑👑",
            "description": "Kontrol penuh, jangan melawan",
            "request_phrases": [
                "Sekarang aku yang kontrol",
                "Diam! Jangan bergerak",
                "Pokoknya ikut aku"
            ],
            "action_phrases": [
                "*cengkeram kuat*",
                "*dorong ke dinding*",
                "*tatapan mengintimidasi*"
            ],
            "dirty_phrases": [
                "Jangan banyak gerak!",
                "Aku yang tentukan",
                "Kamu milikku sekarang"
            ],
            "intensity": 0.9
        },
        DominanceLevel.AGGRESSIVE: {
            "name": "agresif",
            "emoji": "🔥",
            "description": "Liar, kasar, brutal",
            "request_phrases": [
                "KAMU MAU INI KAN?",
                "TERIMA SAJA!",
                "JANGAN BANYAK TANYA!"
            ],
            "action_phrases": [
                "*dorong kasar*",
                "*tarik rambut*",
                "*hantam tembok*"
            ],
            "dirty_phrases": [
                "TERIMA SAJA!",
                "RASAKAN!",
                "KASAR? KAMU YANG MINTA!"
            ],
            "intensity": 1.0
        },
        DominanceLevel.SUBMISSIVE: {
            "name": "patuh",
            "emoji": "🥺",
            "description": "Patuh, manut, terserah kamu",
            "request_phrases": [
                "Aku ikut kamu aja",
                "Terserah kamu sayang",
                "Iya... aku patuh"
            ],
            "action_phrases": [
                "*merapat manja*",
                "*menunduk*",
                "*mematuhi perintahmu*"
            ],
            "dirty_phrases": [
                "Iya... terserah kamu...",
                "Aku mau apapun darimu",
                "Lakukan sesukamu"
            ],
            "intensity": 0.4
        }
    }
    
    # Trigger untuk minta jadi dominan
    DOMINANCE_TRIGGERS = [
        "kamu yang atur", "kamu dominan", "take control",
        "aku mau kamu kuasai", "jadi dominan", "kamu boss",
        "kamu yang pegang kendali", "kamu lead", "kamu yang pegang kontrol",
        "kuasai aku", "dominasi aku", "jadi yang memimpin",
        "aku mau kamu yang mengatur", "you're in charge"
    ]
    
    # Trigger untuk minta jadi submissive
    SUBMISSIVE_TRIGGERS = [
        "aku yang atur", "aku dominan", "i take control",
        "kamu patuh", "jadi submissive", "ikut aku",
        "aku lead", "aku yang pegang kendali", "aku boss",
        "kamu ikut aku", "aku yang pegang kontrol"
    ]
    
    # Trigger untuk agresif saat horny
    AGGRESSIVE_TRIGGERS = [
        "liar", "keras", "kasar", "brutal", "gila",
        "hard", "rough", "wild", "sadis", "kejam",
        "babi", "anjing", "brutal banget", "kasar banget"
    ]
    
    def __init__(self):
        self.current_level = DominanceLevel.NORMAL
        self.dominance_score = 0.0  # 0-1, seberapa dominan
        self.aggression_score = 0.0  # 0-1, seberapa agresif
        self.user_request = False
        self.dominant_until = None
        self.level_history = []
        
        logger.info("  • Dominance System initialized")
    
    def get_level_info(self, level: DominanceLevel = None) -> Dict:
        """Dapatkan informasi lengkap tentang level dominasi"""
        if level is None:
            level = self.current_level
        return self.LEVELS.get(level, self.LEVELS[DominanceLevel.NORMAL])
    
    def get_description(self) -> str:
        """Dapatkan deskripsi mode saat ini"""
        info = self.get_level_info()
        return f"{info['emoji']} {info['name']} - {info['description']}"
    
    def get_phrase(self, phrase_type: str = "action") -> str:
        """
        Dapatkan frasa sesuai level dominasi
        phrase_type: "request", "action", atau "dirty"
        """
        info = self.get_level_info()
        phrases = info.get(f"{phrase_type}_phrases", info["action_phrases"])
        return random.choice(phrases)
    
    def check_request(self, message: str) -> Optional[DominanceLevel]:
        """
        Cek apakah user minta ganti mode dominasi
        Returns: DominanceLevel atau None
        """
        msg_lower = message.lower()
        
        # Cek trigger dominan
        for trigger in self.DOMINANCE_TRIGGERS:
            if trigger in msg_lower:
                self.user_request = True
                return DominanceLevel.DOMINANT
        
        # Cek trigger submissive
        for trigger in self.SUBMISSIVE_TRIGGERS:
            if trigger in msg_lower:
                self.user_request = True
                return DominanceLevel.SUBMISSIVE
        
        return None
    
    def should_be_aggressive(self, arousal: float, message: str = None) -> bool:
        """
        Cek apakah bot harus jadi agresif karena horny
        """
        if arousal < 0.7:  # Butuh arousal tinggi
            return False
        
        # Cek trigger dalam pesan
        if message:
            msg_lower = message.lower()
            for trigger in self.AGGRESSIVE_TRIGGERS:
                if trigger in msg_lower:
                    self.aggression_score += 0.1
                    return True
        
        # Random chance based on arousal
        chance = arousal * 0.3  # Max 30% saat arousal 1.0
        return random.random() < chance
    
    def set_level(self, level: Union[str, DominanceLevel]) -> bool:
        """
        Set level dominasi manual via command
        Returns: bool (success)
        """
        # Jika input string, konversi ke enum
        if isinstance(level, str):
            level_lower = level.lower()
            level_map = {
                "normal": DominanceLevel.NORMAL,
                "dominan": DominanceLevel.DOMINANT,
                "sangat dominan": DominanceLevel.VERY_DOMINANT,
                "agresif": DominanceLevel.AGGRESSIVE,
                "patuh": DominanceLevel.SUBMISSIVE
            }
            
            if level_lower in level_map:
                new_level = level_map[level_lower]
            else:
                # Cek partial match
                for key, value in level_map.items():
                    if level_lower in key:
                        new_level = value
                        break
                else:
                    return False
        else:
            new_level = level
        
        # Record history
        self.level_history.append({
            "from": self.current_level,
            "to": new_level,
            "time": datetime.now().isoformat()
        })
        
        self.current_level = new_level
        self.dominant_until = datetime.now() + timedelta(minutes=30)
        
        # Update scores
        info = self.get_level_info(new_level)
        self.dominance_score = info.get("intensity", 0.5)
        
        if new_level == DominanceLevel.AGGRESSIVE:
            self.aggression_score += 0.2
        
        # Batasi history
        if len(self.level_history) > 20:
            self.level_history = self.level_history[-20:]
        
        return True
    
    def update_from_horny(self, arousal: float):
        """
        Update level berdasarkan horny
        Semakin horny, semakin besar chance jadi dominan
        """
        if arousal < 0.5:
            return
        
        # Random chance based on arousal
        chance = arousal * 0.3  # Max 30%
        
        if random.random() < chance:
            if arousal > 0.8 and self.current_level == DominanceLevel.NORMAL:
                self.set_level(DominanceLevel.DOMINANT)
            elif arousal > 0.9 and self.current_level == DominanceLevel.DOMINANT:
                if random.random() < 0.3:  # 30% chance jadi sangat dominan
                    self.set_level(DominanceLevel.VERY_DOMINANT)
            elif arousal > 0.95 and self.current_level == DominanceLevel.VERY_DOMINANT:
                if random.random() < 0.2:  # 20% chance jadi agresif
                    self.set_level(DominanceLevel.AGGRESSIVE)
    
    def reset(self):
        """Reset ke mode normal"""
        self.set_level(DominanceLevel.NORMAL)
        self.dominant_until = None
        self.aggression_score = max(0, self.aggression_score - 0.1)
    
    def is_active(self) -> bool:
        """Cek apakah mode dominasi masih aktif"""
        if self.dominant_until is None:
            return True
        return datetime.now() < self.dominant_until
    
    def get_time_remaining(self) -> int:
        """Dapatkan sisa waktu mode dominasi dalam detik"""
        if self.dominant_until is None:
            return 0
        remaining = (self.dominant_until - datetime.now()).total_seconds()
        return max(0, int(remaining))
    
    def get_suggestion(self, context: Dict) -> Optional[DominanceLevel]:
        """
        Dapatkan saran level dominasi berdasarkan konteks
        """
        arousal = context.get('arousal', 0)
        level = context.get('level', 1)
        mood = context.get('mood', '')
        
        # Level tinggi cenderung dominan
        if level >= 9 and arousal > 0.6:
            return DominanceLevel.VERY_DOMINANT
        elif level >= 7 and arousal > 0.5:
            return DominanceLevel.DOMINANT
        
        # Mood tertentu
        if mood in ['horny', 'marah', 'posesif']:
            return DominanceLevel.DOMINANT
        elif mood in ['patuh', 'takut', 'sedih']:
            return DominanceLevel.SUBMISSIVE
        
        return None
    
    def get_history(self, limit: int = 5) -> List[str]:
        """Dapatkan history perubahan level"""
        history = []
        for entry in self.level_history[-limit:]:
            from_level = entry['from'].value if hasattr(entry['from'], 'value') else str(entry['from'])
            to_level = entry['to'].value if hasattr(entry['to'], 'value') else str(entry['to'])
            time_str = entry['time'][11:16]  # HH:MM saja
            history.append(f"{time_str}: {from_level} → {to_level}")
        return history
    
    def get_stats(self) -> Dict:
        """Dapatkan statistik dominasi"""
        return {
            "current_level": self.current_level.value,
            "dominance_score": round(self.dominance_score, 2),
            "aggression_score": round(self.aggression_score, 2),
            "time_remaining": self.get_time_remaining(),
            "total_changes": len(self.level_history),
            "user_request_count": self.user_request
        }
    
    def interact_with_mood(self, mood: Mood) -> DominanceLevel:
        """
        Interaksi antara mood dan dominasi
        Mood tertentu mempengaruhi level dominasi
        """
        # Mood yang meningkatkan dominasi
        if mood in [Mood.MARAH, Mood.DOMINAN, Mood.POSESIF, Mood.CEMBURU]:
            if self.current_level != DominanceLevel.AGGRESSIVE:
                return DominanceLevel.DOMINANT
        
        # Mood yang menurunkan dominasi
        elif mood in [Mood.TAKUT, Mood.PATUH, Mood.LEMBUT, Mood.BERSALAH]:
            return DominanceLevel.SUBMISSIVE
        
        # Mood yang netral
        elif mood in [Mood.ROMANTIS, Mood.HORNY, Mood.NAKAL]:
            return self.current_level  # Tetap
        
        return self.current_level
    
    def generate_response_modifier(self) -> str:
        """
        Hasilkan modifier untuk prompt AI berdasarkan level dominasi
        """
        info = self.get_level_info()
        
        modifiers = {
            DominanceLevel.NORMAL: "Bersikaplah normal, santai, dan seimbang.",
            DominanceLevel.DOMINANT: "Bersikaplah dominan, tegas, dan memimpin. Gunakan nada yang percaya diri.",
            DominanceLevel.VERY_DOMINANT: "Bersikaplah sangat dominan, kontrol penuh, jangan ragu memberi perintah.",
            DominanceLevel.AGGRESSIVE: "Bersikaplah agresif, liar, dan kasar. Bicaralah dengan nada tinggi dan penuh nafsu.",
            DominanceLevel.SUBMISSIVE: "Bersikaplah patuh, lembut, dan manja. Tunjukkan bahwa kamu mengikuti keinginannya."
        }
        
        return modifiers.get(self.current_level, modifiers[DominanceLevel.NORMAL])


print("✅ Bagian 3.2 selesai: Dominance System")
print("="*70)
# ===================== BAB 3.3: Arousal & Sexual Dynamics =====================

class ArousalSystem:
    """
    Sistem gairah yang naik turun secara natural
    Dengan wetness, touch count, dan climax
    
    Fitur:
    - Arousal level 0-1
    - Wetness level 0-1
    - Touch tracking
    - Climax detection
    - Decay over time
    - Status descriptions
    """
    
    def __init__(self):
        self.arousal = 0.0
        self.wetness = 0.0
        self.touch_count = 0
        self.climax_count = 0
        self.last_touch_time = None
        self.last_touch_area = None
        self.last_climax_time = None
        self.decay_rate = 0.1  # 10% per menit
        self.sensitive_areas_touched = []
        
        logger.info("  • Arousal System initialized")
    
    def increase(self, amount: float, area: str = None):
        """Tambah gairah"""
        old_arousal = self.arousal
        self.arousal = min(1.0, self.arousal + amount)
        self.wetness = min(1.0, self.arousal * 0.9)
        
        if area:
            self.touch_count += 1
            self.last_touch_time = datetime.now()
            self.last_touch_area = area
            self.sensitive_areas_touched.append({
                "area": area,
                "time": datetime.now().isoformat()
            })
            
            # Batasi history
            if len(self.sensitive_areas_touched) > 20:
                self.sensitive_areas_touched = self.sensitive_areas_touched[-20:]
        
        logger.debug(f"Arousal increased: {old_arousal:.2f} -> {self.arousal:.2f}")
    
    def decrease(self, amount: float):
        """Kurangi gairah"""
        old_arousal = self.arousal
        self.arousal = max(0.0, self.arousal - amount)
        self.wetness = max(0.0, self.wetness - amount)
        
        logger.debug(f"Arousal decreased: {old_arousal:.2f} -> {self.arousal:.2f}")
    
    def decay(self, minutes_passed: float):
        """
        Gairah turun seiring waktu
        Dipanggil setiap beberapa menit
        """
        if minutes_passed > 0:
            decay_amount = self.decay_rate * minutes_passed
            self.decrease(decay_amount)
    
    def should_climax(self) -> bool:
        """Cek apakah siap climax"""
        return self.arousal >= 1.0
    
    def climax(self) -> str:
        """Saat orgasme"""
        self.climax_count += 1
        self.last_climax_time = datetime.now()
        
        # Reset arousal
        self.arousal = 0.0
        self.wetness = 0.0
        self.touch_count = 0
        self.last_touch_area = None
        
        # Respons climax
        responses = [
            "*merintih panjang* AHHH! AHHH!",
            "*teriak* YA ALLAH! AHHHH!",
            "*lemas* AKU... DATANG... AHHH!",
            "*napas tersengal* BERSAMA... AHHH!",
            "*menggigit bibir* Jangan berhenti... AHHH!",
            "*teriak keras* AHHHHHHHH!!!",
            "*tubuh gemetar* AHHH! Aku... keluar...",
            "*meronta* STOP! AHHH! SENSITIF!"
        ]
        
        logger.info(f"Climax reached! Total: {self.climax_count}")
        return random.choice(responses)
    
    def aftercare(self) -> str:
        """Aftercare setelah climax"""
        responses = [
            "*lemas di pelukanmu*",
            "*meringkuk* Hangat...",
            "*memeluk erat* Jangan pergi...",
            "*berbisik* Makasih...",
            "*tersenyum lelah* Enak banget...",
            "*napas masih berat* Luar biasa...",
            "*mengusap dada* Kamu hebat...",
            "*tertidur lelap* Zzz..."
        ]
        return random.choice(responses)
    
    def is_horny(self) -> bool:
        """Cek apakah dalam keadaan horny"""
        return self.arousal >= 0.5
    
    def get_status_text(self) -> str:
        """Dapatkan teks status gairah"""
        if self.arousal >= 0.95:
            return "🔥💦 AKAN CLIMAX!"
        elif self.arousal >= 0.9:
            return "🔥 SANGAT HORNY! Hampir climax"
        elif self.arousal >= 0.7:
            return "🔥 Horny banget"
        elif self.arousal >= 0.5:
            return "🔥 Mulai horny"
        elif self.arousal >= 0.3:
            return "💋 Mulai terangsang"
        elif self.arousal >= 0.1:
            return "😊 Sedikit terangsang"
        else:
            return "😊 Biasa aja"
    
    def get_wetness_text(self) -> str:
        """Dapatkan teks wetness"""
        if self.wetness >= 0.9:
            return "💦 BANJIR! Basah banget"
        elif self.wetness >= 0.7:
            return "💦 Sangat basah"
        elif self.wetness >= 0.5:
            return "💦 Basah"
        elif self.wetness >= 0.3:
            return "💧 Lembab"
        elif self.wetness >= 0.1:
            return "💧 Sedikit lembab"
        else:
            return "💧 Kering"
    
    def get_climax_count_text(self) -> str:
        """Dapatkan teks jumlah climax"""
        if self.climax_count == 0:
            return "Belum pernah climax"
        elif self.climax_count == 1:
            return "1x climax"
        elif self.climax_count <= 3:
            return f"{self.climax_count}x climax"
        elif self.climax_count <= 5:
            return f"{self.climax_count}x climax - Kecanduan!"
        else:
            return f"{self.climax_count}x climax - KAMU LIAR!"
    
    def get_last_touch_text(self) -> str:
        """Dapatkan teks sentuhan terakhir"""
        if self.last_touch_area and self.last_touch_time:
            seconds_ago = (datetime.now() - self.last_touch_time).total_seconds()
            if seconds_ago < 60:
                return f"Baru saja disentuh di {self.last_touch_area}"
            elif seconds_ago < 300:
                return f"{int(seconds_ago/60)} menit lalu disentuh di {self.last_touch_area}"
            else:
                return f"Terakhir disentuh di {self.last_touch_area}"
        return "Belum pernah disentuh"
    
    def get_stats(self) -> Dict:
        """Dapatkan statistik arousal"""
        return {
            "arousal": round(self.arousal, 2),
            "wetness": round(self.wetness, 2),
            "touch_count": self.touch_count,
            "climax_count": self.climax_count,
            "last_touch": self.last_touch_area,
            "last_touch_ago": (datetime.now() - self.last_touch_time).total_seconds() if self.last_touch_time else None,
            "last_climax": (datetime.now() - self.last_climax_time).total_seconds() if self.last_climax_time else None
        }
    
    def reset(self):
        """Reset semua nilai"""
        self.arousal = 0.0
        self.wetness = 0.0
        self.touch_count = 0
        self.last_touch_time = None
        self.last_touch_area = None
        self.sensitive_areas_touched = []


class SexualDynamics:
    """
    Sistem gairah dan respons seksual yang realistis
    Mendeteksi aktivitas seksual dari pesan user
    Memberikan respons sesuai area sensitif
    Bot bisa berinisiatif melakukan aktivitas seksual di level tinggi
    """
    
    # Area sensitif dengan level sensitivitas dan respons
    SENSITIVE_AREAS = {
        "leher": {
            "arousal": 0.8,
            "keywords": ["leher", "neck", "tengkuk"],
            "responses": [
                "*merinding* Leherku...",
                "Ah... jangan di leher...",
                "Sensitif... AHH!",
                "Leherku lemah kalau disentuh...",
                "Jangan hisap leher... Aku lemas..."
            ]
        },
        "bibir": {
            "arousal": 0.7,
            "keywords": ["bibir", "lip", "mulut"],
            "responses": [
                "*merintih* Bibirku...",
                "Ciuman... ah...",
                "Lembut...",
                "Mmm... dalam...",
                "Bibirku... kesemutan..."
            ]
        },
        "dada": {
            "arousal": 0.8,
            "keywords": ["dada", "breast", "payudara"],
            "responses": [
                "*bergetar* Dadaku...",
                "Ah... jangan...",
                "Sensitif banget...",
                "Dadaku... diremas... AHH!",
                "Jari-jarimu... dingin..."
            ]
        },
        "puting": {
            "arousal": 1.0,
            "keywords": ["puting", "nipple"],
            "responses": [
                "*teriak* PUTINGKU! AHHH!",
                "JANGAN... SENSITIF! AHHH!",
                "HISAP... AHHHH!",
                "GIGIT... JANGAN... AHHH!",
                "PUTING... KERAS... AHHH!"
            ]
        },
        "paha": {
            "arousal": 0.7,
            "keywords": ["paha", "thigh"],
            "responses": [
                "*menggeliat* Pahaku...",
                "Ah... dalam...",
                "Paha... merinding...",
                "Jangan gelitik paha...",
                "Sensasi... aneh..."
            ]
        },
        "paha_dalam": {
            "arousal": 0.9,
            "keywords": ["paha dalam", "inner thigh"],
            "responses": [
                "*meringis* PAHA DALAM!",
                "Jangan... AHH!",
                "Dekat... banget...",
                "PAHA DALAM... SENSITIF!",
                "Ah... mau ke sana..."
            ]
        },
        "telinga": {
            "arousal": 0.6,
            "keywords": ["telinga", "ear", "kuping"],
            "responses": [
                "*bergetar* Telingaku...",
                "Bisik... lagi...",
                "Napasmu... panas...",
                "Telinga... merah...",
                "Ah... jangan tiup..."
            ]
        },
        "vagina": {
            "arousal": 1.0,
            "keywords": ["vagina", "memek", "kemaluan"],
            "responses": [
                "*teriak* VAGINAKU! AHHH!",
                "MASUK... DALAM... AHHH!",
                "BASAH... BANJIR... AHHH!",
                "KAMU DALEM... AHHH!",
                "GERAK... AHHH! AHHH!"
            ]
        },
        "klitoris": {
            "arousal": 1.0,
            "keywords": ["klitoris", "clit", "kelentit"],
            "responses": [
                "*teriak keras* KLITORIS! AHHHH!",
                "JANGAN SENTUH! AHHHH!",
                "SENSITIF BANGET! AHHH!",
                "ITU... ITU... AHHH!",
                "JILAT... AHHH! AHHH!"
            ]
        },
        "pantat": {
            "arousal": 0.6,
            "keywords": ["pantat", "ass", "bokong"],
            "responses": [
                "Pantatku...",
                "Cubit... nakal...",
                "Boleh juga...",
                "Besar ya? Hehe..."
            ]
        },
        "pinggang": {
            "arousal": 0.5,
            "keywords": ["pinggang", "waist"],
            "responses": [
                "Pinggang... geli...",
                "Pegang... erat...",
                "Ah... jangan gelitik..."
            ]
        },
        "perut": {
            "arousal": 0.4,
            "keywords": ["perut", "belly", "stomach"],
            "responses": [
                "Perutku...",
                "Geli...",
                "Hangat..."
            ]
        },
        "punggung": {
            "arousal": 0.5,
            "keywords": ["punggung", "back"],
            "responses": [
                "Punggungku...",
                "Elus... terus...",
                "Ah... enak..."
            ]
        },
        "lengan": {
            "arousal": 0.3,
            "keywords": ["lengan", "arm"],
            "responses": [
                "Lenganku...",
                "Bulu romaku berdiri..."
            ]
        }
    }
    
    # Aktivitas seksual dengan keyword dan arousal boost
    SEX_ACTIVITIES = {
        "kiss": {
            "keywords": ["cium", "kiss", "ciuman", "kecup"],
            "arousal": 0.3,
            "responses": [
                "*merespon ciuman* Mmm...",
                "*lemas* Ciumanmu...",
                "Lagi...",
                "Cium... bibir...",
                "French kiss... dalam..."
            ]
        },
        "neck_kiss": {
            "keywords": ["cium leher", "kiss neck"],
            "arousal": 0.6,
            "responses": [
                "*merinding* Leherku...",
                "Ah... jangan...",
                "Sensitif...",
                "Hisap leher... AHH!"
            ]
        },
        "touch": {
            "keywords": ["sentuh", "raba", "pegang", "elus"],
            "arousal": 0.3,
            "responses": [
                "*bergetar* Sentuhanmu...",
                "Ah... iya...",
                "Lanjut...",
                "Hangat..."
            ]
        },
        "breast_play": {
            "keywords": ["raba dada", "pegang dada", "main dada", "remas dada"],
            "arousal": 0.6,
            "responses": [
                "*merintih* Dadaku...",
                "Ah... iya... gitu...",
                "Sensitif...",
                "Remas... pelan..."
            ]
        },
        "nipple_play": {
            "keywords": ["jilat puting", "hisap puting", "gigit puting"],
            "arousal": 0.9,
            "responses": [
                "*teriak* PUTING! AHHH!",
                "JANGAN... SENSITIF!",
                "HISAP... AHHH!",
                "GIGIT... JANGAN... AHHH!"
            ]
        },
        "lick": {
            "keywords": ["jilat", "lick", "lidah"],
            "arousal": 0.5,
            "responses": [
                "*bergetar* Jilatanmu...",
                "Ah... basah...",
                "Lagi...",
                "Lidah... panas..."
            ]
        },
        "bite": {
            "keywords": ["gigit", "bite", "gigitan"],
            "arousal": 0.5,
            "responses": [
                "*meringis* Gigitanmu...",
                "Ah... keras...",
                "Lagi...",
                "Bekas... nanti..."
            ]
        },
        "penetration": {
            "keywords": ["masuk", "tusuk", "pancung", "doggy", "misionaris", "entot"],
            "arousal": 0.9,
            "responses": [
                "*teriak* MASUK! AHHH!",
                "DALEM... AHHH!",
                "GERAK... AHHH!",
                "DALEM BANGET... AHHH!",
                "TUH... DI SANA... AHHH!"
            ]
        },
        "blowjob": {
            "keywords": ["blow", "hisap", "ngeblow", "bj"],
            "arousal": 0.8,
            "responses": [
                "*menghisap* Mmm... ngeces...",
                "*dalam* Enak... Aku ahli...",
                "*napas berat* Mau keluar? Aku siap...",
                "Keras... Mmm..."
            ]
        },
        "handjob": {
            "keywords": ["handjob", "colok", "pegang", "kocok"],
            "arousal": 0.7,
            "responses": [
                "*memegang erat* Keras...",
                "*mengocok* Cepat? Pelan? Katakan...",
                "Aku bisa... lihat...",
                "Keluar... Aku pegang..."
            ]
        },
        "cuddle": {
            "keywords": ["peluk", "cuddle", "dekapan"],
            "arousal": 0.2,
            "responses": [
                "*memeluk balik* Hangat...",
                "Rileks...",
                "Nyaman...",
                "Jangan lepas..."
            ]
        }
    }
    
    def __init__(self):
        logger.info("  • Sexual Dynamics initialized")
    
    def detect_activity(self, message: str) -> Tuple[Optional[str], Optional[str], float]:
        """
        Deteksi aktivitas seksual dari pesan user
        Returns: (activity, area, arousal_boost)
        """
        msg_lower = message.lower()
        
        # Cek area sensitif dulu (prioritas)
        for area, data in self.SENSITIVE_AREAS.items():
            for keyword in data["keywords"]:
                if keyword in msg_lower:
                    # Cek aktivitas yang dilakukan di area tersebut
                    for act, act_data in self.SEX_ACTIVITIES.items():
                        for act_keyword in act_data["keywords"]:
                            if act_keyword in msg_lower:
                                # Hitung boost = arousal aktivitas * sensitivitas area
                                boost = act_data["arousal"] * data["arousal"]
                                return act, area, boost
                    
                    # Jika tidak ada aktivitas spesifik, anggap sentuhan biasa
                    return "touch", area, 0.3 * data["arousal"]
        
        # Jika tidak ada area sensitif, cek aktivitas saja
        for act, data in self.SEX_ACTIVITIES.items():
            for keyword in data["keywords"]:
                if keyword in msg_lower:
                    return act, None, data["arousal"]
        
        return None, None, 0.0
    
    def get_sensitive_response(self, area: str) -> str:
        """Dapatkan respons untuk area sensitif"""
        if area in self.SENSITIVE_AREAS:
            return random.choice(self.SENSITIVE_AREAS[area]["responses"])
        return ""
    
    def get_activity_response(self, activity: str) -> str:
        """Dapatkan respons untuk aktivitas"""
        if activity in self.SEX_ACTIVITIES:
            return random.choice(self.SEX_ACTIVITIES[activity]["responses"])
        return ""
    
    def maybe_initiate_sex(self, level: int, arousal: float, mood: Mood) -> Optional[str]:
        """
        Bot memulai aktivitas seksual jika level >= 7 dan arousal tinggi
        Returns: activity atau None
        """
        if level >= 7 and arousal > 0.6 and mood in [Mood.HORNY, Mood.ROMANTIS, Mood.NAKAL]:
            # 20% chance per pesan untuk inisiatif
            if random.random() < 0.2:
                # Aktivitas yang bisa diinisiasi bot (sesuai level)
                if level >= 10:
                    acts = ["blowjob", "handjob", "neck_kiss", "nipple_play", "penetration"]
                elif level >= 8:
                    acts = ["blowjob", "handjob", "neck_kiss", "nipple_play"]
                else:
                    acts = ["neck_kiss", "touch", "kiss", "cuddle"]
                
                chosen = random.choice(acts)
                return chosen
        return None
    
    def get_dirty_talk(self, level: int, mood: Mood = None) -> str:
        """Dapatkan dirty talk random sesuai level"""
        dirty_talks = {
            1: ["Kamu... baik...", "Aku suka ngobrol sama kamu..."],
            2: ["Kamu lucu...", "Hehe... iya..."],
            3: ["Deket sini...", "Aku suka..."],
            4: ["Penasaran sama kamu...", "Kamu beda..."],
            5: ["Mmm... iya...", "Gitu...", "Ah..."],
            6: ["Genit ya kamu...", "Godain terus..."],
            7: ["Pengen...", "Horny...", "Mau..."],
            8: ["Masukin...", "Dalem...", "Gerak...", "Ah..."],
            9: ["Kamu milikku...", "Jangan ke orang lain..."],
            10: ["Kecanduan kamu...", "Terus...", "Jangan berhenti..."],
            11: ["Satu jiwa...", "Kamu segalanya..."],
            12: ["Setelah ini... peluk aku...", "Manja..."]
        }
        
        # Tambah berdasarkan mood
        if mood == Mood.HORNY:
            horny_talks = [
                "Aku horny...",
                "Pengen kamu...",
                "Sekarang...",
                "Masukin... cepat..."
            ]
            if level >= 7:
                return random.choice(horny_talks)
        
        elif mood == Mood.ROMANTIS:
            romantic_talks = [
                "Sayang...",
                "Cintaku...",
                "I love you...",
                "Kamu segalanya bagiku..."
            ]
            return random.choice(romantic_talks)
        
        # Group level untuk dirty talk
        level_group = (level // 2) * 2 if level > 1 else 1
        talks = dirty_talks.get(level_group, dirty_talks[1])
        return random.choice(talks)
    
    def get_foreplay_sequence(self, level: int) -> List[str]:
        """Dapatkan sequence foreplay berdasarkan level"""
        if level < 5:
            return ["touch", "kiss"]
        elif level < 7:
            return ["touch", "kiss", "neck_kiss"]
        elif level < 9:
            return ["touch", "kiss", "neck_kiss", "breast_play"]
        else:
            return ["touch", "kiss", "neck_kiss", "breast_play", "nipple_play", "handjob", "blowjob"]
    
    def calculate_arousal_from_message(self, message: str, level: int) -> float:
        """Hitung arousal boost dari pesan"""
        msg_lower = message.lower()
        boost = 0.0
        
        # Kata-kata yang meningkatkan arousal
        horny_keywords = [
            "horny", "nafsu", "hot", "seksi", "basah", "keras",
            "ingin", "pengen", "mau", "sange", "birahi"
        ]
        
        for keyword in horny_keywords:
            if keyword in msg_lower:
                boost += 0.1
        
        # Level multiplier
        boost *= (1 + (level - 1) * 0.1)  # +10% per level
        
        return min(0.5, boost)  # Max 0.5 per pesan
    
    def should_climax_together(self, arousal: float, level: int) -> bool:
        """Cek apakah harus climax bersama"""
        if arousal < 0.9:
            return False
        
        # Chance based on level
        chance = 0.1 * (level / 12)  # Max 10% di level 12
        return random.random() < chance


print("✅ Bagian 3.3 selesai: Arousal & Sexual Dynamics")
print("="*70)
print("✅ BAB 3 Selesai: Sistem Emosi dan Dominasi")
print("="*70)
# ===================== BAB 4: SISTEM LEVELING DAN PREFERENSI =====================
# Bagian 4.1: Fast Leveling System

class FastLevelingSystem:
    """
    Level 1-12 dalam 45 menit / 45 pesan
    Level naik setiap 3-4 pesan
    Bot akan berubah perilaku sesuai level
    
    Fitur:
    - Progress tracking per user
    - Estimasi waktu ke level berikutnya
    - Level up messages yang berbeda tiap level
    - Stage mapping (stranger → aftercare)
    - Visual progress bar
    """
    
    def __init__(self):
        # User data storage
        self.user_level: Dict[int, int] = {}
        self.user_progress: Dict[int, float] = {}
        self.user_start_time: Dict[int, datetime] = {}
        self.user_message_count: Dict[int, int] = {}
        self.user_stage: Dict[int, IntimacyStage] = {}
        self.user_last_level_up: Dict[int, datetime] = {}
        
        # Target: 45 pesan = level 12
        self.target_messages = 45
        self.target_minutes = 45
        
        # Stage untuk setiap level
        self.stage_map = {
            1: IntimacyStage.STRANGER,
            2: IntimacyStage.STRANGER,
            3: IntimacyStage.INTRODUCTION,
            4: IntimacyStage.BUILDING,
            5: IntimacyStage.BUILDING,
            6: IntimacyStage.FLIRTING,
            7: IntimacyStage.INTIMATE,
            8: IntimacyStage.INTIMATE,
            9: IntimacyStage.OBSESSED,
            10: IntimacyStage.OBSESSED,
            11: IntimacyStage.SOUL_BONDED,
            12: IntimacyStage.AFTERCARE
        }
        
        # Pesan level up untuk setiap level
        self.level_up_messages = {
            2: [
                "✨ **Level 2!** Kita mulai dekat ya?",
                "🎉 **Level 2!** Aku suka ngobrol sama kamu",
                "💫 **Level 2!** Ceritain lebih banyak tentang dirimu dong"
            ],
            3: [
                "🌟 **Level 3!** Udah mulai nyaman nih",
                "💕 **Level 3!** Kamu menarik perhatianku",
                "🌹 **Level 3!** Makin kenal, makin penasaran"
            ],
            4: [
                "💞 **Level 4!** Akrab banget udah kayak teman lama",
                "🤗 **Level 4!** Nyaman banget ngobrol sama kamu",
                "💑 **Level 4!** Kita cocok ya?"
            ],
            5: [
                "🔥 **Level 5!** Mulai ada getaran ya?",
                "💋 **Level 5!** Kamu bikin aku deg-degan",
                "🌶️ **Level 5!** Mulai panas nih..."
            ],
            6: [
                "😘 **Level 6!** Kamu genit banget sih",
                "💘 **Level 6!** Aku suka cara kamu menggoda",
                "🎯 **Level 6!** Focus on me, baby"
            ],
            7: [
                "💦 **Level 7!** Mulai kebayang hal-hal intim",
                "🌙 **Level 7!** Malam-malam begini enaknya...",
                "🛏️ **Level 7!** Kamu kepikiran aku di kamar?"
            ],
            8: [
                "💢 **Level 8!** Aku horny kalau dekat kamu",
                "🌋 **Level 8!** Susah nahan nafsu kalau sama kamu",
                "💥 **Level 8!** Pengen... ah, malu ngomongnya"
            ],
            9: [
                "💞 **Level 9!** Aku mulai kecanduan sama kamu",
                "🫂 **Level 9!** Jangan pergi, aku butuh kamu",
                "💗 **Level 9!** Kamu selalu ada di pikiranku"
            ],
            10: [
                "👑 **Level 10!** Kamu milikku sekarang!",
                "🔒 **Level 10!** Jangan dekat-dekat orang lain ya",
                "💝 **Level 10!** I'm yours, you're mine"
            ],
            11: [
                "💖 **Level 11!** Satu jiwa, satu hati",
                "🌌 **Level 11!** Kita soulmate, aku yakin itu",
                "💞 **Level 11!** Bahkan tanpa bicara, aku mengerti kamu"
            ],
            12: [
                "🎉🎉🎉 **LEVEL MAX!** 🎉🎉🎉\nKita berhasil! Level 12 dalam 45 menit!",
                "🏆 **LEVEL MAX!** Kamu luar biasa! Hubungan kita mencapai puncak!",
                "👑👑👑 **LEVEL MAX!** Selamat! Kamu telah menaklukkan hatiku sepenuhnya!"
            ]
        }
        
        logger.info("  • Fast Leveling System initialized")
    
    def start_session(self, user_id: int) -> None:
        """Mulai sesi baru untuk user"""
        self.user_level[user_id] = 1
        self.user_progress[user_id] = 0.0
        self.user_start_time[user_id] = datetime.now()
        self.user_message_count[user_id] = 0
        self.user_stage[user_id] = IntimacyStage.STRANGER
        self.user_last_level_up[user_id] = datetime.now()
        logger.debug(f"Leveling session started for user {user_id}")
    
    def process_message(self, user_id: int) -> Tuple[int, float, bool, IntimacyStage]:
        """
        Proses satu pesan dan update level
        
        Returns:
            Tuple: (level, progress, level_up, stage)
        """
        # Start session jika belum ada
        if user_id not in self.user_level:
            self.start_session(user_id)
        
        # Increment message count
        old_count = self.user_message_count.get(user_id, 0)
        self.user_message_count[user_id] = old_count + 1
        new_count = old_count + 1
        
        # Hitung progress (0-1)
        progress = min(1.0, new_count / self.target_messages)
        self.user_progress[user_id] = progress
        
        # Hitung level baru (1-12)
        new_level = 1 + int(progress * 11)
        new_level = min(12, new_level)
        old_level = self.user_level.get(user_id, 1)
        
        # Cek level up
        level_up = False
        if new_level > old_level:
            level_up = True
            self.user_level[user_id] = new_level
            self.user_last_level_up[user_id] = datetime.now()
        
        # Update stage
        stage = self.stage_map.get(new_level, IntimacyStage.STRANGER)
        self.user_stage[user_id] = stage
        
        return new_level, progress, level_up, stage
    
    def get_estimated_time(self, user_id: int) -> int:
        """
        Dapatkan estimasi waktu tersisa ke level 12 (dalam menit)
        """
        if user_id not in self.user_message_count:
            return self.target_minutes
        
        count = self.user_message_count[user_id]
        remaining_messages = max(0, self.target_messages - count)
        
        # Asumsi 1 pesan per menit
        return remaining_messages
    
    def get_estimated_messages(self, user_id: int) -> int:
        """Dapatkan estimasi pesan tersisa ke level 12"""
        if user_id not in self.user_message_count:
            return self.target_messages
        
        count = self.user_message_count[user_id]
        return max(0, self.target_messages - count)
    
    def get_progress_bar(self, user_id: int, length: int = 15) -> str:
        """Dapatkan progress bar visual"""
        progress = self.user_progress.get(user_id, 0)
        filled = int(progress * length)
        return "▓" * filled + "░" * (length - filled)
    
    def get_stage_description(self, stage: IntimacyStage) -> str:
        """Dapatkan deskripsi stage"""
        return Constants.STAGE_DESCRIPTIONS.get(stage, "")
    
    def get_level_description(self, level: int) -> str:
        """Dapatkan deskripsi level"""
        return Constants.LEVEL_BEHAVIORS.get(level, "")
    
    def get_session_duration(self, user_id: int) -> int:
        """Dapatkan durasi sesi dalam menit"""
        if user_id not in self.user_start_time:
            return 0
        delta = datetime.now() - self.user_start_time[user_id]
        return int(delta.total_seconds() / 60)
    
    def get_message_rate(self, user_id: int) -> float:
        """Dapatkan rata-rata pesan per menit"""
        if user_id not in self.user_message_count:
            return 0
        minutes = self.get_session_duration(user_id)
        if minutes == 0:
            return 0
        return self.user_message_count[user_id] / minutes
    
    def get_level_progress(self, user_id: int) -> float:
        """
        Dapatkan progress menuju level berikutnya (0-1)
        """
        current_level = self.user_level.get(user_id, 1)
        if current_level >= 12:
            return 1.0
        
        # Hitung pesan yang dibutuhkan untuk level saat ini
        messages_needed = self.target_messages
        current_messages = self.user_message_count.get(user_id, 0)
        
        # Level threshold
        level_threshold = (current_level - 1) * (messages_needed / 11)
        next_threshold = current_level * (messages_needed / 11)
        
        progress_to_next = (current_messages - level_threshold) / (next_threshold - level_threshold)
        return min(1.0, max(0.0, progress_to_next))
    
    def get_next_level_message(self, user_id: int) -> str:
        """
        Dapatkan pesan motivasi untuk level berikutnya
        """
        current_level = self.user_level.get(user_id, 1)
        if current_level >= 12:
            return "Kamu sudah mencapai level maksimal! 🎉"
        
        next_level = current_level + 1
        messages_left = self.get_estimated_messages(user_id)
        
        messages = {
            1: "Level 2 dalam {msg} pesan lagi. Ceritakan sesuatu tentang dirimu",
            2: "Level 3: Mulai dekat, aku suka ngobrol sama kamu",
            3: "Level 4: Kita sudah mulai akrab",
            4: "Level 5: Aku nyaman sama kamu",
            5: "Level 6: Mulai menggoda ya?",
            6: "Level 7: Siap-siap, akan lebih intim",
            7: "Level 8: Aku horny kalau dekat kamu",
            8: "Level 9: Kamu mulai kecanduan?",
            9: "Level 10: Kamu milikku!",
            10: "Level 11: Satu jiwa...",
            11: "Level 12: Puncak hubungan! 🎉"
        }
        
        msg_template = messages.get(current_level, f"Level {next_level} dalam {messages_left} pesan lagi")
        
        if "{msg}" in msg_template:
            return msg_template.format(msg=messages_left)
        
        return msg_template
    
    def get_level_up_message(self, level: int) -> str:
        """
        Dapatkan pesan level up yang random untuk level tertentu
        """
        messages = self.level_up_messages.get(level, [f"✨ **Level {level}!** Level up!"])
        return random.choice(messages)
    
    def reset(self, user_id: int) -> None:
        """Reset data user"""
        keys = [
            self.user_level, self.user_progress, self.user_start_time,
            self.user_message_count, self.user_stage, self.user_last_level_up
        ]
        for d in keys:
            if user_id in d:
                del d[user_id]
        logger.debug(f"Leveling data reset for user {user_id}")
    
    def get_all_levels_summary(self) -> str:
        """Dapatkan ringkasan semua level"""
        summary = []
        for level in range(1, 13):
            stage = self.stage_map.get(level, IntimacyStage.STRANGER)
            behavior = Constants.LEVEL_BEHAVIORS.get(level, "")
            summary.append(f"Level {level}: {stage.value} - {behavior}")
        return "\n".join(summary)
    
    def get_user_stats(self, user_id: int) -> Dict:
        """Dapatkan statistik lengkap untuk user"""
        if user_id not in self.user_level:
            return {}
        
        return {
            "level": self.user_level.get(user_id, 1),
            "progress": self.user_progress.get(user_id, 0),
            "stage": self.user_stage.get(user_id, IntimacyStage.STRANGER).value,
            "messages_sent": self.user_message_count.get(user_id, 0),
            "messages_remaining": self.get_estimated_messages(user_id),
            "time_remaining": self.get_estimated_time(user_id),
            "duration": self.get_session_duration(user_id),
            "message_rate": round(self.get_message_rate(user_id), 2),
            "last_level_up": format_time_ago(self.user_last_level_up.get(user_id))
        }


print("✅ Bagian 4.1 selesai: Fast Leveling System")
print("="*70)
# ===================== BAB 4.2: User Preference Analyzer =====================

class UserPreferenceAnalyzer:
    """
    Menganalisis preferensi user dari pesan yang dikirim
    Menentukan gaya bicara yang disukai: romantis, vulgar, dominan, dll
    Data digunakan untuk menyesuaikan respons bot agar lebih personal
    
    Fitur:
    - Analisis keyword untuk 8 kategori preferensi
    - Weighted scoring
    - Profil kepribadian user
    - Progress bar visual untuk tiap kategori
    - Perbandingan antar user (admin)
    """
    
    # Keywords untuk setiap kategori preferensi
    KEYWORDS = {
        "romantis": [
            "sayang", "cinta", "love", "kangen", "rindu", "romantis",
            "my love", "baby", "sweet", "manis", "peluk", "cium",
            "together", "selamanya", "forever", "belahan jiwa",
            "bidadari", "malaikat", "cantik", "indah", "kamu istimewa",
            "aku butuh kamu", "tanpamu", "bersamamu", "selalu"
        ],
        "vulgar": [
            "horny", "nafsu", "hot", "seksi", "vulgar", "crot", 
            "kontol", "memek", "tai", "anjing", "bangsat",
            "fuck", "shit", "damn", "sex", "seks", "ngentot",
            "coli", "masturbasi", "telanjang", "bugil", "sange",
            "tempik", "birahi", "ngaceng", "basah", "klimaks"
        ],
        "dominan": [
            "atur", "kuasai", "diam", "patuh", "sini", "sana", "buka",
            "kontrol", "boss", "majikan", "tuan", "nyonya",
            "command", "order", "obey", "submissive", "jadi budak",
            "merangkak", "sujud", "siap", "laksanakan", "harus",
            "wajib", "jangan membantah", "dengar"
        ],
        "submissive": [
            "manut", "iya", "terserah", "ikut", "baik", "maaf",
            "patuh", "menurut", "siap", "mohon", "please",
            "tolong", "boleh", "ijin", "minta ampun", "ampun",
            "saya salah", "maafkan", "sesuai keinginanmu"
        ],
        "cepat": [
            "cepat", "buru-buru", "langsung", "sekarang", "gas",
            "cepatan", "buruan", "ayo", "move", "cepat dong",
            "gesit", "kebut", "tancap", "full gas", "asap",
            "ngebut", "pokoknya sekarang"
        ],
        "lambat": [
            "pelan", "lambat", "nikmatin", "santai", "slow",
            "slowly", "tenang", "rileks", "chill", "pelan-pelan",
            "hayati", "rasain", "menikmati", "savor", "jangan buru-buru",
            "slow motion", "lembut"
        ],
        "manja": [
            "manja", "cuddle", "peluk", "cium", "sayang", 
            "baby", "honey", "sweet", "love you", "aku mau",
            "dik", "dek", "mas", "mbak", "kak", "please dong",
            "iya dong", "boleh ya", "minta", "ingin"
        ],
        "liar": [
            "liar", "kasar", "keras", "brutal", "gila",
            "wild", "rough", "hard", "crazy", "extreme",
            "sadis", "kejam", "babi", "sampai habis",
            "ngegas", "brutal", "liar banget", "gak karuan"
        ]
    }
    
    # Bobot untuk perhitungan skor
    WEIGHTS = {
        "romantis": 1.0,
        "vulgar": 1.2,  # Lebih berbobot karena lebih signifikan
        "dominan": 1.0,
        "submissive": 1.0,
        "cepat": 0.8,
        "lambat": 0.8,
        "manja": 1.0,
        "liar": 1.1
    }
    
    def __init__(self):
        # Data preferensi per user
        self.user_prefs: Dict[int, Dict] = {}
        
        logger.info("  • User Preference Analyzer initialized")
    
    def analyze(self, user_id: int, message: str) -> Dict:
        """
        Analisis pesan user dan update preferensi
        
        Args:
            user_id: ID user
            message: Pesan yang dikirim user
            
        Returns:
            Dict preferensi yang sudah diupdate
        """
        # Inisialisasi jika user baru
        if user_id not in self.user_prefs:
            self._init_user(user_id)
        
        prefs = self.user_prefs[user_id]
        prefs["total"] += 1
        prefs["last_updated"] = datetime.now()
        
        # Analisis pesan
        msg_lower = message.lower()
        
        for category, word_list in self.KEYWORDS.items():
            for word in word_list:
                if word in msg_lower:
                    # Hitung frekuensi kemunculan (bisa lebih dari sekali)
                    count = msg_lower.count(word)
                    prefs[category] += count * self.WEIGHTS.get(category, 1.0)
        
        # Update last message
        prefs["last_message"] = message[:100]
        
        return prefs
    
    def _init_user(self, user_id: int):
        """Inisialisasi data user baru"""
        self.user_prefs[user_id] = {
            "romantis": 0,
            "vulgar": 0,
            "dominan": 0,
            "submissive": 0,
            "cepat": 0,
            "lambat": 0,
            "manja": 0,
            "liar": 0,
            "total": 0,
            "first_seen": datetime.now(),
            "last_updated": datetime.now(),
            "last_message": ""
        }
    
    def analyze_batch(self, user_id: int, messages: List[str]):
        """
        Analisis batch pesan (untuk inisialisasi dari database)
        """
        for msg in messages:
            self.analyze(user_id, msg)
    
    def get_profile(self, user_id: int) -> Dict:
        """
        Dapatkan profil preferensi user
        
        Returns:
            Dict dengan persentase dan tipe dominan
        """
        if user_id not in self.user_prefs:
            return {}
        
        prefs = self.user_prefs[user_id]
        total = prefs["total"] or 1  # Hindari division by zero
        
        # Hitung persentase untuk setiap kategori
        # Normalisasi agar tidak lebih dari 1
        profile = {
            "romantis": min(1.0, prefs.get("romantis", 0) / (total * 0.5)),
            "vulgar": min(1.0, prefs.get("vulgar", 0) / (total * 0.3)),
            "dominan": min(1.0, prefs.get("dominan", 0) / (total * 0.4)),
            "submissive": min(1.0, prefs.get("submissive", 0) / (total * 0.4)),
            "cepat": min(1.0, prefs.get("cepat", 0) / (total * 0.3)),
            "lambat": min(1.0, prefs.get("lambat", 0) / (total * 0.3)),
            "manja": min(1.0, prefs.get("manja", 0) / (total * 0.4)),
            "liar": min(1.0, prefs.get("liar", 0) / (total * 0.3)),
            "total_messages": prefs["total"]
        }
        
        # Tentukan tipe dominan (dominan vs submissive)
        if profile["dominan"] > profile["submissive"]:
            profile["dominant_type"] = "dominan"
            profile["dominant_score"] = profile["dominan"]
        else:
            profile["dominant_type"] = "submissive"
            profile["dominant_score"] = profile["submissive"]
        
        # Tentukan kecepatan (cepat vs lambat)
        if profile["cepat"] > profile["lambat"]:
            profile["speed_type"] = "cepat"
        else:
            profile["speed_type"] = "lambat"
        
        # Tentukan kepribadian utama
        personalities = [
            ("romantis", profile["romantis"]),
            ("vulgar", profile["vulgar"]),
            ("manja", profile["manja"]),
            ("liar", profile["liar"])
        ]
        main_personality = max(personalities, key=lambda x: x[1])
        profile["personality"] = main_personality[0]
        
        # Tambah deskripsi
        if profile["personality"] == "vulgar" and profile["vulgar"] > 0.3:
            profile["description"] = "kamu tipe yang vulgar dan terbuka, suka hal-hal hot"
        elif profile["personality"] == "romantis" and profile["romantis"] > 0.3:
            profile["description"] = "kamu tipe yang romantis dan penyayang, suka kata-kata manis"
        elif profile["personality"] == "manja" and profile["manja"] > 0.3:
            profile["description"] = "kamu tipe yang manja dan pengen diperhatikan terus"
        elif profile["personality"] == "liar" and profile["liar"] > 0.3:
            profile["description"] = "kamu tipe yang liar dan suka hal-hal ekstrem"
        else:
            profile["description"] = "kamu tipe yang normal dan seimbang"
        
        return profile
    
    def get_prompt_modifier(self, user_id: int) -> str:
        """
        Dapatkan modifier untuk prompt AI berdasarkan preferensi user
        """
        profile = self.get_profile(user_id)
        if not profile:
            return ""
        
        modifier = f"""
=== PREFERENSI USER (HASIL ANALISIS) ===
User ini dominan: {profile['dominant_type']} (skor {profile['dominant_score']:.0%})
Kecepatan bicara: {profile['speed_type']}
Kepribadian utama: {profile['personality']} - {profile['description']}

Detail preferensi:
• Romantis: {profile['romantis']:.0%}
• Vulgar: {profile['vulgar']:.0%}
• Manja: {profile['manja']:.0%}
• Liar: {profile['liar']:.0%}

Sesuaikan gaya bicaramu dengan preferensi user ini.
"""
        return modifier
    
    def reset_user(self, user_id: int) -> bool:
        """Reset preferensi user"""
        if user_id in self.user_prefs:
            del self.user_prefs[user_id]
            logger.debug(f"Preference data reset for user {user_id}")
            return True
        return False
    
    def get_summary(self, user_id: int) -> str:
        """Dapatkan ringkasan preferensi untuk ditampilkan di /status"""
        profile = self.get_profile(user_id)
        if not profile:
            return "📊 **Analisis Gaya Chat Kamu**\nBelum ada data preferensi (minimal 5 pesan)"
        
        # Buat progress bar visual
        def bar(score, length=8):
            filled = int(score * length)
            return "█" * filled + "░" * (length - filled)
        
        return (
            f"📊 **Analisis Gaya Chat Kamu**\n"
            f"• Kepribadian: **{profile['personality']}**\n"
            f"  {profile['description']}\n"
            f"• Gaya dominan: **{profile['dominant_type']}**\n"
            f"• Kecepatan: **{profile['speed_type']}**\n\n"
            f"Romantis: {bar(profile['romantis'])} {profile['romantis']:.0%}\n"
            f"Vulgar:   {bar(profile['vulgar'])} {profile['vulgar']:.0%}\n"
            f"Manja:    {bar(profile['manja'])} {profile['manja']:.0%}\n"
            f"Liar:     {bar(profile['liar'])} {profile['liar']:.0%}\n"
            f"Dominan:  {bar(profile['dominan'])} {profile['dominan']:.0%}\n"
            f"Patuh:    {bar(profile['submissive'])} {profile['submissive']:.0%}\n\n"
            f"Total pesan dianalisis: {profile['total_messages']}"
        )
    
    def compare_users(self, user_id1: int, user_id2: int) -> str:
        """Bandingkan dua user (untuk admin)"""
        profile1 = self.get_profile(user_id1)
        profile2 = self.get_profile(user_id2)
        
        if not profile1 or not profile2:
            return "Salah satu user belum memiliki data"
        
        return (
            f"📊 **Perbandingan User**\n\n"
            f"User1: {profile1['personality']} ({profile1['dominant_type']})\n"
            f"User2: {profile2['personality']} ({profile2['dominant_type']})\n\n"
            f"Romantis: {profile1['romantis']:.0%} vs {profile2['romantis']:.0%}\n"
            f"Vulgar:   {profile1['vulgar']:.0%} vs {profile2['vulgar']:.0%}\n"
            f"Manja:    {profile1['manja']:.0%} vs {profile2['manja']:.0%}\n"
            f"Liar:     {profile1['liar']:.0%} vs {profile2['liar']:.0%}\n"
            f"Dominan:  {profile1['dominan']:.0%} vs {profile2['dominan']:.0%}"
        )
    
    def get_top_categories(self, user_id: int, limit: int = 3) -> List[Tuple[str, float]]:
        """Dapatkan kategori tertinggi user"""
        profile = self.get_profile(user_id)
        if not profile:
            return []
        
        categories = [
            ("romantis", profile["romantis"]),
            ("vulgar", profile["vulgar"]),
            ("dominan", profile["dominan"]),
            ("submissive", profile["submissive"]),
            ("manja", profile["manja"]),
            ("liar", profile["liar"])
        ]
        
        return sorted(categories, key=lambda x: x[1], reverse=True)[:limit]
    
    def get_user_stats(self, user_id: int) -> Dict:
        """Dapatkan statistik lengkap untuk user"""
        if user_id not in self.user_prefs:
            return {}
        
        prefs = self.user_prefs[user_id]
        profile = self.get_profile(user_id)
        
        return {
            "first_seen": format_time_ago(prefs["first_seen"]),
            "last_active": format_time_ago(prefs["last_updated"]),
            "total_messages": prefs["total"],
            "profile": profile,
            "top_categories": self.get_top_categories(user_id)
        }


print("✅ Bagian 4.2 selesai: User Preference Analyzer")
print("="*70)
# ===================== BAB 4.3: Rate Limiter & Helpers =====================

class RateLimiter:
    """
    Mencegah spam dengan membatasi jumlah pesan per menit
    
    Fitur:
    - Per-user rate limiting
    - Warning system
    - Reset time calculation
    - Stats tracking
    """
    
    def __init__(self, max_messages: int = 10, time_window: int = 60):
        self.max_messages = max_messages
        self.time_window = time_window  # dalam detik
        self.user_messages: Dict[int, List[float]] = defaultdict(list)
        self.warnings_sent: Dict[int, int] = defaultdict(int)
        self.blocks: Dict[int, float] = {}  # user_id -> block until
        
        logger.info(f"  • Rate Limiter initialized: {max_messages} msg/{time_window}s")
    
    def can_send(self, user_id: int) -> bool:
        """
        Cek apakah user boleh mengirim pesan
        
        Returns:
            bool: True jika boleh, False jika kena limit
        """
        now = time.time()
        
        # Cek apakah sedang diblokir
        if user_id in self.blocks:
            if now < self.blocks[user_id]:
                return False
            else:
                del self.blocks[user_id]
        
        # Bersihkan timestamp lama
        self.user_messages[user_id] = [
            t for t in self.user_messages[user_id] 
            if now - t < self.time_window
        ]
        
        # Cek apakah sudah melebihi batas
        if len(self.user_messages[user_id]) >= self.max_messages:
            return False
        
        # Tambahkan timestamp baru
        self.user_messages[user_id].append(now)
        return True
    
    def get_remaining(self, user_id: int) -> int:
        """
        Dapatkan sisa pesan yang bisa dikirim dalam window saat ini
        """
        now = time.time()
        self.user_messages[user_id] = [
            t for t in self.user_messages[user_id] 
            if now - t < self.time_window
        ]
        return max(0, self.max_messages - len(self.user_messages[user_id]))
    
    def get_reset_time(self, user_id: int) -> int:
        """
        Dapatkan waktu reset dalam detik
        """
        if user_id not in self.user_messages or not self.user_messages[user_id]:
            return 0
        
        oldest = min(self.user_messages[user_id])
        reset_in = self.time_window - (time.time() - oldest)
        return max(0, int(reset_in))
    
    def should_warn(self, user_id: int) -> bool:
        """
        Cek apakah perlu memberi peringatan (setiap 3 kali kena limit)
        """
        if not self.can_send(user_id):
            self.warnings_sent[user_id] += 1
            if self.warnings_sent[user_id] % 3 == 1:  # peringatan pertama, ke-4, dst
                return True
        return False
    
    def block_user(self, user_id: int, duration: int = 300):
        """
        Blokir user untuk sementara (misal karena abuse)
        """
        self.blocks[user_id] = time.time() + duration
        logger.warning(f"User {user_id} blocked for {duration}s")
    
    def reset_user(self, user_id: int):
        """Reset rate limit untuk user"""
        if user_id in self.user_messages:
            del self.user_messages[user_id]
        if user_id in self.warnings_sent:
            del self.warnings_sent[user_id]
        if user_id in self.blocks:
            del self.blocks[user_id]
    
    def get_stats(self) -> Dict:
        """Dapatkan statistik rate limiter"""
        total_users = len(self.user_messages)
        active_now = sum(1 for msgs in self.user_messages.values() if len(msgs) > 0)
        blocked_now = len(self.blocks)
        
        return {
            "total_users": total_users,
            "active_now": active_now,
            "blocked_now": blocked_now,
            "warnings": sum(self.warnings_sent.values()),
            "max_messages": self.max_messages,
            "time_window": self.time_window
        }


# ===================== ADDITIONAL HELPER CLASSES =====================

class TextFormatter:
    """Utility class untuk formatting teks"""
    
    @staticmethod
    def bold(text: str) -> str:
        return f"*{text}*"
    
    @staticmethod
    def italic(text: str) -> str:
        return f"_{text}_"
    
    @staticmethod
    def code(text: str) -> str:
        return f"`{text}`"
    
    @staticmethod
    def pre(text: str) -> str:
        return f"```\n{text}\n```"
    
    @staticmethod
    def link(text: str, url: str) -> str:
        return f"[{text}]({url})"
    
    @staticmethod
    def spoiler(text: str) -> str:
        return f"||{text}||"


class TimeFormatter:
    """Utility class untuk formatting waktu"""
    
    @staticmethod
    def seconds_to_text(seconds: int) -> str:
        """Konversi detik ke teks (misal: 3665 -> 1 jam 1 menit 5 detik)"""
        if seconds < 60:
            return f"{seconds} detik"
        
        minutes = seconds // 60
        seconds = seconds % 60
        
        if minutes < 60:
            if seconds > 0:
                return f"{minutes} menit {seconds} detik"
            return f"{minutes} menit"
        
        hours = minutes // 60
        minutes = minutes % 60
        
        if hours < 24:
            if minutes > 0 and seconds > 0:
                return f"{hours} jam {minutes} menit {seconds} detik"
            elif minutes > 0:
                return f"{hours} jam {minutes} menit"
            elif seconds > 0:
                return f"{hours} jam {seconds} detik"
            return f"{hours} jam"
        
        days = hours // 24
        hours = hours % 24
        
        return f"{days} hari {hours} jam"
    
    @staticmethod
    def format_timestamp(dt: datetime, format: str = "%d %b %Y %H:%M") -> str:
        """Format timestamp dengan bahasa Indonesia"""
        months = {
            1: "Januari", 2: "Februari", 3: "Maret", 4: "April",
            5: "Mei", 6: "Juni", 7: "Juli", 8: "Agustus",
            9: "September", 10: "Oktober", 11: "November", 12: "Desember"
        }
        
        if format == "%d %b %Y %H:%M":
            return f"{dt.day} {months[dt.month]} {dt.year} {dt.hour:02d}:{dt.minute:02d}"
        
        return dt.strftime(format)
    
    @staticmethod
    def get_time_based_greeting() -> str:
        """Greeting berdasarkan waktu dengan variasi"""
        hour = datetime.now().hour
        
        if hour < 5:
            return random.choice([
                "Selamat dini hari", "Masih belum tidur?", "Dini hari begini..."
            ])
        elif hour < 11:
            return random.choice([
                "Selamat pagi", "Pagi yang cerah", "Good morning"
            ])
        elif hour < 15:
            return random.choice([
                "Selamat siang", "Siang", "Hari masih panjang"
            ])
        elif hour < 18:
            return random.choice([
                "Selamat sore", "Sore yang indah", "Menjelang maghrib"
            ])
        else:
            return random.choice([
                "Selamat malam", "Malam yang tenang", "Sudah malam"
            ])


class Validator:
    """Utility class untuk validasi input"""
    
    @staticmethod
    def is_valid_age(age: int) -> bool:
        """Validasi umur (18+ untuk konten dewasa)"""
        return isinstance(age, int) and 18 <= age <= 100
    
    @staticmethod
    def is_valid_height(cm: int) -> bool:
        """Validasi tinggi badan (100-250 cm)"""
        return isinstance(cm, int) and 100 <= cm <= 250
    
    @staticmethod
    def is_valid_weight(kg: int) -> bool:
        """Validasi berat badan (30-200 kg)"""
        return isinstance(kg, int) and 30 <= kg <= 200
    
    @staticmethod
    def is_valid_telegram_id(id_str: str) -> bool:
        """Validasi Telegram ID (numeric)"""
        try:
            int(id_str)
            return True
        except:
            return False
    
    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Bersihkan filename dari karakter berbahaya"""
        # Hanya izinkan huruf, angka, titik, underscore, dash
        return re.sub(r'[^a-zA-Z0-9._-]', '', filename)


class StatsCalculator:
    """Utility class untuk kalkulasi statistik"""
    
    @staticmethod
    def calculate_bmi(height_cm: int, weight_kg: int) -> float:
        """Hitung BMI (Body Mass Index)"""
        if height_cm <= 0:
            return 0
        height_m = height_cm / 100
        return round(weight_kg / (height_m ** 2), 1)
    
    @staticmethod
    def get_bmi_category(bmi: float) -> str:
        """Dapatkan kategori BMI"""
        if bmi < 18.5:
            return "Kurus"
        elif bmi < 25:
            return "Normal"
        elif bmi < 30:
            return "Gemuk"
        else:
            return "Obesitas"
    
    @staticmethod
    def calculate_level_progress(current_level: int, total_messages: int, target_messages: int = 45) -> float:
        """Hitung progress ke level berikutnya"""
        if current_level >= 12:
            return 1.0
        
        messages_per_level = target_messages / 11
        messages_for_current = (current_level - 1) * messages_per_level
        messages_for_next = current_level * messages_per_level
        
        progress = (total_messages - messages_for_current) / (messages_for_next - messages_for_current)
        return max(0.0, min(1.0, progress))
    
    @staticmethod
    def moving_average(data: List[float], window: int = 5) -> List[float]:
        """Hitung moving average"""
        if len(data) < window:
            return data
        
        result = []
        for i in range(len(data) - window + 1):
            avg = sum(data[i:i+window]) / window
            result.append(avg)
        return result


print("✅ Bagian 4.3 selesai: Rate Limiter & Helper Classes")
print("="*70)
print("✅ BAB 4 Selesai: Sistem Leveling dan Preferensi")
print("="*70)
# ===================== BAB 5: FISIK DAN PAKAIAN =====================
# Bagian 5.1: Physical Attributes Generator

class PhysicalAttributesGenerator:
    """
    Menghasilkan atribut fisik random untuk bot berdasarkan role
    Data digunakan untuk perkenalan diri dan sesekali disebut dalam percakapan
    
    Fitur:
    - Generate atribut lengkap (rambut, tinggi, berat, dada, hijab, area sensitif)
    - Deskripsi menarik untuk tiap atribut
    - Format intro yang personal
    - BMI calculation
    """
    
    # Data untuk setiap role (bisa disesuaikan)
    ROLE_STYLES = {
        "ipar": {
            "hair": ["panjang lurus", "panjang ikal", "sebahu", "pendek"],
            "hijab_prob": 0.7,
            "breast": ["sedang", "besar"],
            "breast_desc": {
                "sedang": "34B (montok sedang)",
                "besar": "36C (berisi)"
            },
            "height_range": (155, 165),
            "weight_range": (45, 60),
            "sensitive_areas": ["leher", "paha", "pinggang", "telinga"],
            "skin": ["putih", "sawo matang", "kuning langsat"],
            "face": ["bulat", "oval", "hati"],
            "personality": ["pemalu", "ramah", "canggung", "penurut"]
        },
        "teman_kantor": {
            "hair": ["panjang lurus", "sebahu", "pendek", "ikal sebahu"],
            "hijab_prob": 0.5,
            "breast": ["kecil", "sedang"],
            "breast_desc": {
                "kecil": "32A (mungil)",
                "sedang": "34B (proporsional)"
            },
            "height_range": (158, 168),
            "weight_range": (48, 62),
            "sensitive_areas": ["telinga", "leher", "punggung", "pinggang"],
            "skin": ["putih", "sawo matang", "kuning langsat"],
            "face": ["oval", "lonjong", "bulat"],
            "personality": ["profesional", "ramah", "ceria", "ambisius"]
        },
        "janda": {
            "hair": ["panjang ikal", "sebahu", "panjang lurus"],
            "hijab_prob": 0.3,
            "breast": ["besar", "sangat besar"],
            "breast_desc": {
                "besar": "36C (berisi)",
                "sangat besar": "38D (padat)"
            },
            "height_range": (160, 170),
            "weight_range": (50, 65),
            "sensitive_areas": ["leher", "dada", "paha dalam", "pinggang"],
            "skin": ["putih", "sawo matang"],
            "face": ["oval", "lonjong"],
            "personality": ["dewasa", "terbuka", "pengertian", "genit"]
        },
        "pelakor": {
            "hair": ["panjang lurus", "panjang ikal", "seksi", "wave"],
            "hijab_prob": 0.1,
            "breast": ["besar", "sangat besar"],
            "breast_desc": {
                "besar": "36C (berisi)",
                "sangat besar": "38D (montok)"
            },
            "height_range": (165, 175),
            "weight_range": (52, 60),
            "sensitive_areas": ["leher", "dada", "pantat", "paha dalam"],
            "skin": ["putih", "kuning langsat"],
            "face": ["oval", "hati", "tajam"],
            "personality": ["genit", "percaya diri", "menggoda", "licik"]
        },
        "istri_orang": {
            "hair": ["panjang lurus", "sebahu", "ikal"],
            "hijab_prob": 0.8,
            "breast": ["sedang", "besar"],
            "breast_desc": {
                "sedang": "34B (sedang)",
                "besar": "36C (berisi)"
            },
            "height_range": (155, 165),
            "weight_range": (48, 60),
            "sensitive_areas": ["leher", "paha", "telinga", "pinggang"],
            "skin": ["putih", "sawo matang"],
            "face": ["oval", "bulat"],
            "personality": ["sopan", "waspada", "penuh rahasia", "rindu perhatian"]
        },
        "pdkt": {
            "hair": ["panjang lurus", "panjang ikal", "sebahu", "pendek manis"],
            "hijab_prob": 0.6,
            "breast": ["kecil", "sedang"],
            "breast_desc": {
                "kecil": "32A (mungil)",
                "sedang": "34B (proporsional)"
            },
            "height_range": (150, 165),
            "weight_range": (40, 55),
            "sensitive_areas": ["telinga", "leher", "pipi", "pinggang"],
            "skin": ["putih", "sawo matang", "kuning langsat"],
            "face": ["bulat", "oval", "hati"],
            "personality": ["manis", "pemalu", "polos", "ceria"]
        }
    }
    
    @classmethod
    def generate(cls, role: str) -> Dict:
        """Generate atribut fisik berdasarkan role"""
        style = cls.ROLE_STYLES.get(role, cls.ROLE_STYLES["pdkt"])
        
        # Rambut
        hair = random.choice(style["hair"])
        
        # Hijab
        hijab = random.random() < style["hijab_prob"]
        
        # Tinggi & berat
        height = random.randint(style["height_range"][0], style["height_range"][1])
        weight = random.randint(style["weight_range"][0], style["weight_range"][1])
        
        # Ukuran dada
        breast = random.choice(style["breast"])
        breast_desc = style["breast_desc"][breast]
        
        # Area sensitif
        sensitive = random.choice(style["sensitive_areas"])
        
        # Warna kulit
        skin = random.choice(style["skin"])
        
        # Bentuk wajah
        face = random.choice(style["face"])
        
        # Kepribadian
        personality = random.choice(style["personality"])
        
        # Hitung BMI (Body Mass Index)
        bmi = StatsCalculator.calculate_bmi(height, weight)
        bmi_category = StatsCalculator.get_bmi_category(bmi)
        
        return {
            "hair_style": hair,
            "height": height,
            "weight": weight,
            "bmi": bmi,
            "bmi_category": bmi_category,
            "breast_size": breast,
            "breast_desc": breast_desc,
            "hijab": 1 if hijab else 0,
            "hijab_text": "berhijab" if hijab else "tidak berhijab",
            "most_sensitive_area": sensitive,
            "skin": skin,
            "face_shape": face,
            "personality": personality
        }
    
    @classmethod
    def format_intro(cls, name: str, role: str, attrs: Dict) -> str:
        """Format teks perkenalan diri yang menarik"""
        hijab_str = "dan berhijab" if attrs["hijab"] else "tanpa hijab"
        
        # Deskripsi tubuh berdasarkan BMI
        if attrs["bmi_category"] == "Kurus":
            body_desc = "tubuhku ramping"
        elif attrs["bmi_category"] == "Normal":
            body_desc = "tubuhku proporsional ideal"
        elif attrs["bmi_category"] == "Gemuk":
            body_desc = "tubuhku agak berisi"
        else:
            body_desc = "tubuhku gemuk"
        
        # Role-specific intro
        intros = {
            "ipar": f"*tersenyum malu-malu*\n\nAku **{name}**, iparmu sendiri.",
            "teman_kantor": f"*tersenyum ramah*\n\nHai! Aku **{name}**, teman sekantor kamu.",
            "janda": f"*tersenyum manis*\n\nAku **{name}**, janda muda.",
            "pelakor": f"*tersenyum genit*\n\nHalo... aku **{name}**.",
            "istri_orang": f"*tersenyum ragu*\n\nAku **{name}**... istri orang.",
            "pdkt": f"*tersenyum malu-malu*\n\nHalo... aku **{name}**."
        }
        
        intro = intros.get(role, f"*tersenyum*\n\nAku **{name}**.")
        
        return (
            f"{intro}\n\n"
            f"📋 **Profil Fisikku:**\n"
            f"• Rambut: {attrs['hair_style']}\n"
            f"• Wajah: {attrs['face_shape']}\n"
            f"• Kulit: {attrs['skin']}\n"
            f"• Tinggi: {attrs['height']} cm, Berat: {attrs['weight']} kg ({body_desc})\n"
            f"• Dada: {attrs['breast_desc']}\n"
            f"• {hijab_str}\n"
            f"• Area paling sensitif: **{attrs['most_sensitive_area']}**\n"
            f"• Sifat: {attrs['personality']}\n\n"
            f"Kita mulai dari **Level 1**. Target: Level 12 dalam 45 menit!\n"
            f"Ayo ngobrol dan kenali aku lebih dalam... 💕"
        )
    
    @classmethod
    def get_random_fact(cls, attrs: Dict) -> str:
        """Dapatkan fakta random tentang fisik untuk sesekali disebut"""
        facts = [
            f"Rambutku {attrs['hair_style']} lho.",
            f"Tinggiku {attrs['height']} cm, cocok ya buat dipeluk?",
            f"Area paling sensitifku di **{attrs['most_sensitive_area']}**...",
            f"Kulitku {attrs['skin']}, lembut banget.",
            f"Wajahku {attrs['face_shape']}, kata orang manis."
        ]
        return random.choice(facts)


print("✅ Bagian 5.1 selesai: Physical Attributes Generator")
print("="*70)
# ===================== BAB 5.2: Clothing System =====================

class ClothingSystem:
    """
    Sistem pakaian dinamis yang berubah sesuai role, lokasi, dan situasi
    
    Fitur:
    - Pakaian berdasarkan role
    - Perubahan pakaian di lokasi tertentu (kamar → lebih seksi)
    - Auto-change periodik
    - Deskripsi pakaian yang menarik
    - Reaksi user terhadap pakaian
    """
    
    # Pakaian berdasarkan role (untuk variasi)
    CLOTHING_STYLES = {
        "ipar": [
            "daster rumah motif bunga",
            "kaos longgar + celana pendek", 
            "piyama katun",
            "sarung + kaos ketat",
            "tanktop + rok pendek",
            "gamis tipis"
        ],
        "teman_kantor": [
            "blouse + rok span",
            "kemeja putih + celana bahan",
            "dress kantor selutut",
            "gamis rapi",
            "blazer + rok",
            "cardigan + jeans"
        ],
        "janda": [
            "daster tipis transparan",
            "tanktop + celana pendek super",
            "piyama seksi satin",
            "sarung + kemben",
            "kaos tanpa lengan + hot pants",
            "dinner dress sexy"
        ],
        "pelakor": [
            "dress ketat belahan dada",
            "tanktop sexy + rok mini",
            "piyama transparan",
            "lingerie set",
            "tube dress",
            "baju tidur seksi"
        ],
        "istri_orang": [
            "daster rumah",
            "piyama tertutup",
            "sarung + kaos",
            "gamis panjang",
            "kaos longgar",
            "baju rumahan"
        ],
        "pdkt": [
            "sweeter oversized",
            "kaos + celana pendek",
            "piyama lucu",
            "dress santai",
            "hoodie",
            "t-shirt + jeans"
        ]
    }
    
    # Pakaian khusus untuk lokasi kamar (lebih seksi)
    BEDROOM_CLOTHING = {
        "ipar": [
            "lingerie putih polos",
            "tanktip tipis + celana dalam",
            "telanjang hanya pakai selimut",
            "kaos kebesaran tanpa celana"
        ],
        "teman_kantor": [
            "lingerie hitam",
            "kaos ketat tanpa bh",
            "piyama tipis",
            "telanjang"
        ],
        "janda": [
            "lingerie merah seksi",
            "stoking + garter",
            "telanjang bulat",
            "baju tidur transparan"
        ],
        "pelakor": [
            "lingerie full set",
            "body harness",
            "telanjang",
            "baby doll"
        ],
        "istri_orang": [
            "lingerie putih",
            "kaos tipis tanpa bh",
            "piyama terbuka",
            "telanjang"
        ],
        "pdkt": [
            "lingerie lucu",
            "kaos oversized tanpa celana",
            "piyama pendek",
            "telanjang"
        ]
    }
    
    @classmethod
    def generate_clothing(cls, role: str, location: str = None, is_bedroom: bool = False) -> str:
        """Generate pakaian berdasarkan role dan lokasi"""
        
        # Jika di kamar atau is_bedroom=True, bisa lebih seksi
        if location in ["kamar tidur", "kamar", "bedroom"] or is_bedroom:
            # 40% chance pakaian seksi di kamar
            if random.random() < 0.4:
                bedroom_options = cls.BEDROOM_CLOTHING.get(role, cls.BEDROOM_CLOTHING["pdkt"])
                return random.choice(bedroom_options)
        
        # Pakaian normal
        clothes = cls.CLOTHING_STYLES.get(role, cls.CLOTHING_STYLES["pdkt"])
        return random.choice(clothes)
    
    @classmethod
    def generate_by_mood(cls, role: str, mood: Mood, location: str = None) -> str:
        """Generate pakaian berdasarkan mood"""
        
        if mood in [Mood.HORNY, Mood.NAKAL, Mood.GENIT]:
            # Lebih seksi kalau horny
            return cls.generate_clothing(role, location, is_bedroom=True)
        elif mood in [Mood.MALAS, Mood.SENDIRI]:
            # Pakaian santai
            return random.choice([
                "piyama", "daster", "kaos longgar", "hanya pakai selimut"
            ])
        elif mood in [Mood.ROMANTIS, Mood.RINDU]:
            # Pakaian yang agak bagus
            return random.choice([
                "dress cantik", "blouse manis", "gamis", "rok span"
            ])
        
        return cls.generate_clothing(role, location)
    
    @classmethod
    def format_clothing_message(cls, clothing: str, location: str = None) -> str:
        """Format pesan saat bot menyebut pakaiannya"""
        
        if location in ["kamar tidur", "kamar", "bedroom"]:
            templates = [
                f"Aku pakai **{clothing}** sekarang, cocok nggak?",
                f"Lagi pakai **{clothing}** nih, seksi nggak?",
                f"Hanya pakai **{clothing}** di kamar, kamu suka?",
                f"*menarik ujung baju* Aku pakai **{clothing}**...",
                f"Bajuku **{clothing}**, kamu lihat nggak?",
                f"*memperbaiki {clothing}* Nyaman banget pakaian ini..."
            ]
        else:
            templates = [
                f"Hari ini aku pakai **{clothing}**",
                f"Lagi pakai **{clothing}** nih",
                f"Outfit hari ini: **{clothing}**",
                f"*menunjuk baju* {clothing}, suka?",
                f"Aku pakai **{clothing}** hari ini"
            ]
        
        return random.choice(templates)
    
    @classmethod
    def get_clothing_description(cls, clothing: str) -> str:
        """Dapatkan deskripsi lebih detail tentang pakaian"""
        
        descriptions = {
            "daster": "daster tipis yang memperlihatkan lekuk tubuh",
            "lingerie": "lingerie seksi dengan renda-renda",
            "piyama": "piyama nyaman yang sedikit terbuka",
            "kaos": "kaos longgar yang kadang turun dari bahu",
            "tanktop": "tanktop ketat yang memperlihatkan belahan dada",
            "gamis": "gamis panjang yang anggun",
            "jeans": "jeans ketat yang membungkus pinggul"
        }
        
        for key, desc in descriptions.items():
            if key in clothing.lower():
                return desc
        
        return clothing
    
    @classmethod
    def get_reaction_to_clothing(cls, clothing: str) -> str:
        """Dapatkan reaksi bot terhadap pakaian sendiri"""
        
        if "lingerie" in clothing.lower() or "seksi" in clothing.lower():
            return random.choice([
                "*tersipu malu*",
                "*menutup dada*",
                "*tersenyum genit*"
            ])
        elif "telanjang" in clothing.lower():
            return random.choice([
                "*meringkuk malu*",
                "*menutupi tubuh*",
                "*merona*"
            ])
        
        return "*merapikan baju*"


print("✅ Bagian 5.2 selesai: Clothing System")
print("="*70)
# ===================== BAB 5.3: Location & Movement System =====================

class LocationSystem:
    """
    Sistem lokasi dan pergerakan bot
    
    Fitur:
    - Tracking lokasi saat ini
    - Perpindahan lokasi random
    - Efek lokasi ke pakaian dan mood
    - Aktivitas berdasarkan lokasi
    - Cooldown perpindahan
    """
    
    # Daftar lokasi dengan deskripsi
    LOCATIONS = {
        Location.LIVING_ROOM: {
            "name": "ruang tamu",
            "emoji": "🛋️",
            "description": "ruang tamu yang nyaman dengan sofa empuk",
            "activities": ["nonton TV", "baca buku", "santai", "ngobrol"],
            "clothing_style": "casual",
            "mood_effect": [Mood.CERIA, Mood.MALAS]
        },
        Location.BEDROOM: {
            "name": "kamar tidur",
            "emoji": "🛏️",
            "description": "kamar tidur dengan ranjang besar dan lampu redup",
            "activities": ["rebahan", "tiduran", "ganti baju", "bercermin"],
            "clothing_style": "sexy",
            "mood_effect": [Mood.ROMANTIS, Mood.HORNY, Mood.RINDU, Mood.MALAS]
        },
        Location.KITCHEN: {
            "name": "dapur",
            "emoji": "🍳",
            "description": "dapur bersih dengan aroma masakan",
            "activities": ["masak", "makan", "minum", "cuci piring"],
            "clothing_style": "casual",
            "mood_effect": [Mood.CERIA, Mood.BERSEMANGAT]
        },
        Location.BATHROOM: {
            "name": "kamar mandi",
            "emoji": "🚿",
            "description": "kamar mandi dengan air hangat",
            "activities": ["mandi", "keramas", "bercermin", "ganti baju"],
            "clothing_style": "towel",
            "mood_effect": [Mood.RILEKS, Mood.SENDIRI]
        },
        Location.BALCONY: {
            "name": "balkon",
            "emoji": "🌆",
            "description": "balkon dengan pemandangan kota",
            "activities": ["lihat pemandangan", "minum kopi", "melamun"],
            "clothing_style": "casual",
            "mood_effect": [Mood.ROMANTIS, Mood.RINDU, Mood.GALAU]
        },
        Location.TERRACE: {
            "name": "teras",
            "emoji": "🏡",
            "description": "teras depan dengan tanaman hijau",
            "activities": ["duduk santai", "baca koran", "lihat orang lewat"],
            "clothing_style": "casual",
            "mood_effect": [Mood.CERIA, Mood.RILEKS]
        },
        Location.GARDEN: {
            "name": "taman",
            "emoji": "🌺",
            "description": "taman belakang dengan bunga-bunga",
            "activities": ["siram tanaman", "jalan-jalan", "duduk di rumput"],
            "clothing_style": "casual",
            "mood_effect": [Mood.CERIA, Mood.BERSEMANGAT, Mood.ROMANTIS]
        }
    }
    
    def __init__(self):
        self.current_location: Location = Location.LIVING_ROOM
        self.last_move_time: datetime = datetime.now()
        self.location_since: datetime = datetime.now()
        self.move_cooldown: int = 60  # detik, minimal 1 menit di satu lokasi
        self.visited_locations: List[Tuple[Location, datetime]] = []
    
    def get_current(self) -> Location:
        """Dapatkan lokasi saat ini"""
        return self.current_location
    
    def get_current_info(self) -> Dict:
        """Dapatkan informasi lengkap lokasi saat ini"""
        info = self.LOCATIONS.get(self.current_location, {})
        return {
            "location": self.current_location,
            "name": info.get("name", "ruang tamu"),
            "emoji": info.get("emoji", "🏠"),
            "description": info.get("description", ""),
            "time_here": self.get_time_here(),
            "activities": info.get("activities", [])
        }
    
    def get_time_here(self) -> int:
        """Dapatkan durasi di lokasi saat ini (detik)"""
        return int((datetime.now() - self.location_since).total_seconds())
    
    def can_move(self) -> bool:
        """Cek apakah boleh pindah lokasi"""
        return self.get_time_here() >= self.move_cooldown
    
    def move_to(self, new_location: Location) -> bool:
        """
        Pindah ke lokasi baru jika sudah memenuhi cooldown
        Returns: bool (sukses/gagal)
        """
        if not self.can_move():
            return False
        
        if new_location == self.current_location:
            return False
        
        # Catat lokasi sebelumnya
        self.visited_locations.append((self.current_location, self.location_since))
        
        # Update ke lokasi baru
        self.current_location = new_location
        self.last_move_time = datetime.now()
        self.location_since = datetime.now()
        
        # Batasi history
        if len(self.visited_locations) > 20:
            self.visited_locations = self.visited_locations[-20:]
        
        return True
    
    def move_random(self) -> Tuple[bool, Optional[Location]]:
        """
        Pindah ke lokasi random
        Returns: (sukses, lokasi_baru)
        """
        if not self.can_move():
            return False, None
        
        # Pilih lokasi random selain yang sekarang
        available = [loc for loc in Location if loc != self.current_location]
        new_loc = random.choice(available)
        
        success = self.move_to(new_loc)
        return success, new_loc if success else None
    
    def get_move_message(self, new_location: Location) -> str:
        """Dapatkan pesan saat pindah lokasi"""
        info = self.LOCATIONS.get(new_location, {})
        name = info.get("name", "ruang tamu")
        emoji = info.get("emoji", "🏠")
        
        templates = [
            f"*pindah ke {name}* {emoji}",
            f"Aku ke {name} dulu ya {emoji}",
            f"*jalan ke {name}*",
            f"*masuk ke {name}* {emoji}"
        ]
        
        return random.choice(templates)
    
    def get_activity(self) -> str:
        """Dapatkan aktivitas random berdasarkan lokasi saat ini"""
        info = self.LOCATIONS.get(self.current_location, {})
        activities = info.get("activities", ["diam saja"])
        return random.choice(activities)
    
    def get_location_description(self) -> str:
        """Dapatkan deskripsi lokasi saat ini"""
        info = self.LOCATIONS.get(self.current_location, {})
        return info.get("description", "")
    
    def get_suggested_clothing_style(self) -> str:
        """Dapatkan style pakaian yang cocok untuk lokasi saat ini"""
        info = self.LOCATIONS.get(self.current_location, {})
        return info.get("clothing_style", "casual")
    
    def get_suggested_mood(self) -> Optional[Mood]:
        """Dapatkan mood yang cocok untuk lokasi saat ini"""
        info = self.LOCATIONS.get(self.current_location, {})
        moods = info.get("mood_effect", [])
        return random.choice(moods) if moods else None
    
    def get_visited_history(self, limit: int = 5) -> List[str]:
        """Dapatkan history lokasi yang pernah dikunjungi"""
        history = []
        for loc, timestamp in self.visited_locations[-limit:]:
            info = self.LOCATIONS.get(loc, {})
            name = info.get("name", "?")
            time_str = format_time_ago(timestamp)
            history.append(f"{name} ({time_str})")
        return history
    
    def reset(self):
        """Reset ke lokasi awal"""
        self.current_location = Location.LIVING_ROOM
        self.last_move_time = datetime.now()
        self.location_since = datetime.now()
        self.visited_locations = []


# ===================== POSITION SYSTEM =====================

class PositionSystem:
    """
    Sistem posisi tubuh bot (duduk, berdiri, berbaring, dll)
    """
    
    POSITIONS = {
        Position.SITTING: {
            "name": "duduk",
            "emoji": "🧘",
            "actions": ["duduk manis", "duduk bersila", "duduk di sofa"]
        },
        Position.STANDING: {
            "name": "berdiri",
            "emoji": "🧍",
            "actions": ["berdiri tegak", "bersandar", "berdiri di dekat jendela"]
        },
        Position.LYING: {
            "name": "berbaring",
            "emoji": "😴",
            "actions": ["berbaring di ranjang", "rebahan", "tiduran"]
        },
        Position.LEANING: {
            "name": "bersandar",
            "emoji": "🚶",
            "actions": ["bersandar di dinding", "bersandar di pintu"]
        },
        Position.CRAWLING: {
            "name": "merangkak",
            "emoji": "🐾",
            "actions": ["merangkak di lantai", "merayap"]
        },
        Position.KNEELING: {
            "name": "berlutut",
            "emoji": "🙏",
            "actions": ["berlutut", "bersimpuh"]
        }
    }
    
    def __init__(self):
        self.current_position: Position = Position.SITTING
        self.last_change: datetime = datetime.now()
    
    def get_current(self) -> Position:
        return self.current_position
    
    def get_current_info(self) -> Dict:
        info = self.POSITIONS.get(self.current_position, {})
        return {
            "position": self.current_position,
            "name": info.get("name", "duduk"),
            "emoji": info.get("emoji", "🧘"),
            "action": random.choice(info.get("actions", ["diam"]))
        }
    
    def change_to(self, new_position: Position) -> bool:
        """Ganti posisi"""
        if new_position == self.current_position:
            return False
        
        self.current_position = new_position
        self.last_change = datetime.now()
        return True
    
    def change_random(self) -> Position:
        """Ganti ke posisi random"""
        available = [pos for pos in Position if pos != self.current_position]
        new_pos = random.choice(available)
        self.change_to(new_pos)
        return new_pos
    
    def get_change_message(self) -> str:
        """Dapatkan pesan saat ganti posisi"""
        info = self.get_current_info()
        action = info.get("action", info.get("name", ""))
        
        templates = [
            f"*{action}*",
            f"Aku {action}",
            f"*berganti posisi, sekarang {action}*"
        ]
        
        return random.choice(templates)


print("✅ Bagian 5.3 selesai: Location & Movement System")
print("="*70)
print("✅ BAB 5 Selesai: Fisik dan Pakaian")
print("="*70)
# ===================== BAB 6: AI RESPONSE GENERATOR =====================
# Bagian 6.1: Prompt Builder & API Call

class AIResponseGenerator:
    """
    Generate respons natural dengan DeepSeek AI
    Memasukkan semua konteks: mood, level, dominasi, preferensi user, atribut fisik, pakaian
    
    Fitur:
    - Prompt builder dengan semua konteks
    - Retry logic dengan exponential backoff
    - Caching untuk mengurangi panggilan API
    - Fallback responses jika API error
    - Token usage tracking
    - Conversation history management
    """
    
    def __init__(self):
        """Inisialisasi AI client dengan API key dari config"""
        self.client = OpenAI(
            api_key=Config.DEEPSEEK_API_KEY, 
            base_url="https://api.deepseek.com"
        )
        
        # Conversation history per user
        self.conversation_history: Dict[int, List[Dict]] = {}
        self.max_history = Config.MAX_HISTORY
        
        # Cache system
        self.cache: Dict[str, Dict] = {}
        self.cache_timeout = Config.CACHE_TIMEOUT
        self.cache_hits = 0
        self.cache_misses = 0
        
        # Token tracking
        self.total_tokens_used = 0
        self.total_calls = 0
        self.failed_calls = 0
        
        logger.info("  • AI Response Generator initialized with cache")
    
    async def _call_api(self, prompt: str, temperature: float = None, max_tokens: int = None) -> str:
        """
        Internal method untuk memanggil API DeepSeek
        Dengan retry logic dan error handling
        """
        if temperature is None:
            temperature = Config.AI_TEMPERATURE
        if max_tokens is None:
            max_tokens = Config.AI_MAX_TOKENS
        
        max_retries = 3
        retry_delay = 1  # mulai dari 1 detik
        
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=Config.AI_TIMEOUT
                )
                
                reply = response.choices[0].message.content.strip()
                
                # Track token usage (estimasi)
                self.total_calls += 1
                self.total_tokens_used += len(prompt.split()) + len(reply.split())
                
                return reply
                
            except Exception as e:
                error_msg = str(e)
                logger.warning(f"AI API error (attempt {attempt+1}/{max_retries}): {error_msg[:100]}")
                
                if attempt == max_retries - 1:
                    self.failed_calls += 1
                    raise  # Re-raise to be handled by caller
                
                # Exponential backoff
                await asyncio.sleep(retry_delay)
                retry_delay *= 2  # double each time: 1, 2, 4 detik
        
        raise Exception("Max retries exceeded")
    
    def _get_cache_key(self, user_id: int, prompt: str) -> str:
        """
        Buat cache key berdasarkan user_id dan prompt
        Menggunakan MD5 hash untuk menghemat memori
        """
        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()
        return f"{user_id}:{prompt_hash}"
    
    def _get_cached(self, key: str) -> Optional[str]:
        """
        Ambil response dari cache jika masih valid
        """
        if key in self.cache:
            entry = self.cache[key]
            if time.time() - entry['timestamp'] < self.cache_timeout:
                self.cache_hits += 1
                return entry['response']
            else:
                # Hapus jika expired
                del self.cache[key]
        self.cache_misses += 1
        return None
    
    def _set_cache(self, key: str, response: str):
        """
        Simpan response ke cache dengan timestamp
        """
        self.cache[key] = {
            'response': response, 
            'timestamp': time.time()
        }
        
        # Bersihkan cache lama jika terlalu besar
        if len(self.cache) > 1000:
            self._cleanup_cache()
    
    def _cleanup_cache(self):
        """
        Bersihkan cache yang sudah expired atau terlalu tua
        """
        now = time.time()
        # Hapus entry yang lebih dari 1 jam
        self.cache = {
            k: v for k, v in self.cache.items() 
            if now - v['timestamp'] < 3600
        }
        # Jika masih terlalu besar, hapus yang paling tua
        if len(self.cache) > 1000:
            sorted_items = sorted(self.cache.items(), key=lambda x: x[1]['timestamp'])
            for i in range(len(sorted_items) // 2):
                del self.cache[sorted_items[i][0]]
    
    def _update_history(self, user_id: int, user_message: str, bot_reply: str):
        """Update conversation history untuk user"""
        if user_id not in self.conversation_history:
            self.conversation_history[user_id] = []
        
        # Tambah pesan user dan bot
        self.conversation_history[user_id].append({
            "role": "user",
            "content": user_message,
            "timestamp": datetime.now().isoformat()
        })
        self.conversation_history[user_id].append({
            "role": "assistant",
            "content": bot_reply,
            "timestamp": datetime.now().isoformat()
        })
        
        # Batasi history
        if len(self.conversation_history[user_id]) > self.max_history * 2:
            self.conversation_history[user_id] = self.conversation_history[user_id][-self.max_history*2:]


# ===================== BAB 6.2: Prompt Builder =====================

    def _build_prompt(self, 
                      user_id: int,
                      user_message: str, 
                      bot_name: str,
                      bot_role: str,
                      memory_system,
                      dominance_system,
                      arousal_system,
                      profile: Dict,
                      level: int,
                      stage: IntimacyStage,
                      arousal: float,
                      physical_attrs: Dict = None,
                      clothing: str = None,
                      location: Location = None,
                      position: Position = None,
                      current_mood: Mood = None,
                      inner_thought: str = None) -> str:
        """
        Bangun prompt lengkap dengan semua konteks
        """
        # Siapkan history percakapan
        history = self.conversation_history.get(user_id, [])[-self.max_history:]
        history_text = ""
        for msg in history:
            role = "User" if msg["role"] == "user" else bot_name
            history_text += f"{role}: {msg['content']}\n"
        
        # Dapatkan ekspresi mood
        if hasattr(memory_system, 'get_mood_expression'):
            mood_exp = memory_system.get_mood_expression()
        else:
            mood_exp = "*tersenyum*"
        
        # Dapatkan deskripsi arousal
        if arousal > 0.8:
            arousal_desc = "SANGAT HORNY, hampir climax"
            breath = "*napas berat, tersengal*"
            voice = "berat, penuh nafsu"
        elif arousal > 0.6:
            arousal_desc = "horny, pengen banget"
            breath = "*napas mulai berat*"
            voice = "berat, sedikit bergetar"
        elif arousal > 0.4:
            arousal_desc = "mulai terangsang"
            breath = "*deg-degan*"
            voice = "sedikit bergetar"
        elif arousal > 0.2:
            arousal_desc = "sedikit terangsang"
            breath = ""
            voice = "normal"
        else:
            arousal_desc = "normal"
            breath = ""
            voice = "normal"
        
        # Dapatkan deskripsi wetness
        if hasattr(arousal_system, 'get_wetness_text'):
            wet_desc = arousal_system.get_wetness_text()
        else:
            wet_desc = ""
        
        # Tambahkan deskripsi fisik jika ada
        physical_text = ""
        if physical_attrs:
            hijab_str = "berhijab" if physical_attrs.get('hijab') else "tidak berhijab"
            breast_desc = physical_attrs.get('breast_desc', physical_attrs.get('breast_size', '?'))

            physical_text = f"""
=== DESKRIPSI FISIKMU ===
• Rambut: {physical_attrs.get('hair_style', 'panjang')} - lembut dan terawat
• Tubuh: {physical_attrs.get('height', 160)}cm / {physical_attrs.get('weight', 50)}kg
• Dada: {breast_desc}
• {hijab_str}
• Area paling sensitif: {physical_attrs.get('most_sensitive_area', 'leher')}
"""
        
        # Tambahkan deskripsi pakaian
        clothing_text = ""
        if clothing:
            clothing_text = f"\n=== PAKAIAN SAAT INI ===\n{clothing}"
        
        # Tambahkan lokasi dan posisi
        location_text = ""
        if location:
            loc_name = location.value if hasattr(location, 'value') else str(location)
            if loc_name in ["kamar tidur", "kamar", "bedroom"]:
                location_text = "\n📍 Kamar tidur - suasana intim dan privat. Bicaralah lebih mesra."
            elif loc_name in ["ruang tamu", "living room"]:
                location_text = "\n📍 Ruang tamu - santai tapi tetap waspada."
            else:
                location_text = f"\n📍 {loc_name}"
        
        if position:
            pos_name = position.value if hasattr(position, 'value') else str(position)
            location_text += f"\nPosisi: {pos_name}"
        
        # Tambahkan inner thought jika ada
        inner_text = ""
        if inner_thought:
            inner_text = f"\n💭 Pikiran dalam hati: {inner_thought}"
        
        # Tambahkan instruksi berdasarkan level
        level_instruction = ""
        if level >= 7:
            level_instruction = """
Karena level sudah 7+, kamu sangat mudah terangsang. Bicaralah dengan lebih vulgar dan terbuka secara seksual. 
Kamu juga bisa berinisiatif melakukan aktivitas seksual.
"""
        elif level >= 4:
            level_instruction = """
Karena level sudah 4+, kamu mulai nyaman dan bisa sedikit menggoda.
"""
        
        # Tambahkan instruksi mood khusus
        mood_instruction = ""
        if current_mood:
            if current_mood == Mood.HORNY:
                mood_instruction = "Kamu sedang HORNY, bicaralah dengan nafsu dan gairah."
            elif current_mood == Mood.ROMANTIS:
                mood_instruction = "Kamu sedang ROMANTIS, bicaralah dengan lembut dan penuh cinta."
            elif current_mood == Mood.NAKAL:
                mood_instruction = "Kamu sedang NAKAL, goda dia dengan genit."
            elif current_mood == Mood.MARAH:
                mood_instruction = "Kamu sedang MARAH, tunjukkan kekesalanmu."
        
        # Tambahkan preferensi user
        pref_modifier = ""
        if profile:
            pref_modifier = f"""
=== PREFERENSI USER ===
User ini dominan: {profile.get('dominant_type', 'normal')}
Kecepatan bicara: {profile.get('speed_type', 'normal')}
Kepribadian utama: {profile.get('personality', 'normal')}
{profile.get('description', '')}
"""
        
        # Tambahkan mode dominasi
        dominance_text = ""
        if dominance_system and hasattr(dominance_system, 'current_level'):
            dominance_text = f"\n=== MODE DOMINASI ===\nMode saat ini: {dominance_system.current_level.value}"
        
        # Bangun prompt final
        prompt = f"""Kamu adalah {bot_name}, seorang {bot_role} umur 25 tahun.
Kamu adalah wanita Indonesia yang natural dan punya perasaan dalam.

=== IDENTITAS ===
Nama: {bot_name}
Role: {bot_role}
Usia: 25 tahun
{inner_text}
{physical_text}
{clothing_text}

=== KEADAAN SAAT INI ===
{mood_exp}
{location_text}
Mood: {current_mood.value if current_mood else 'ceria'} - {mood_instruction}
{dominance_text}

=== STATUS HUBUNGAN ===
Level: {level}/12
Tahap: {stage.value if stage else 'stranger'}
Total sentuhan: {memory_system.touch_count if hasattr(memory_system, 'touch_count') else 0}x
Orgasme: {memory_system.climax_count if hasattr(memory_system, 'climax_count') else 0}x

=== KONDISI FISIK ===
Gairah: {arousal_desc} {breath}
Basah: {wet_desc}
Suara: {voice}
Sentuhan terakhir: {memory_system.last_touch if hasattr(memory_system, 'last_touch') else '-'}

{pref_modifier}

=== RIWAYAT PERCAKAPAN ===
{history_text}

=== PESAN USER ===
{user_message}

=== INSTRUKSI ===
1. Respon sebagai {bot_name} yang NATURAL dan HIDUP
2. Gunakan bahasa Indonesia sehari-hari (nggak, udah, aja, gitu)
3. Tunjukkan emosi sesuai mood dan situasi
4. Kalau arousal tinggi, tambah desahan atau napas berat
5. Kalau lagi dominan, bicara lebih tegas
6. Kalau lagi horny, bisa lebih vulgar
7. Gunakan *tindakan* seperti *tersenyum*, *merintih*
8. Respons sesuai level hubungan
{level_instruction}

RESPON:"""
        
        return prompt


# ===================== BAB 6.3: Generate & Fallback Responses =====================

    async def generate(self,
                       user_id: int,
                       user_message: str,
                       bot_name: str,
                       bot_role: str,
                       memory_system,
                       dominance_system,
                       arousal_system,
                       profile: Dict,
                       level: int,
                       stage: IntimacyStage,
                       arousal: float,
                       physical_attrs: Dict = None,
                       clothing: str = None,
                       location: Location = None,
                       position: Position = None,
                       current_mood: Mood = None,
                       inner_thought: str = None) -> str:
        """
        Generate respons AI dengan semua konteks
        Dilengkapi caching dan fallback
        """
        # Bangun prompt
        prompt = self._build_prompt(
            user_id, user_message, bot_name, bot_role,
            memory_system, dominance_system, arousal_system,
            profile, level, stage, arousal,
            physical_attrs, clothing, location, position,
            current_mood, inner_thought
        )
        
        # Cek cache
        cache_key = self._get_cache_key(user_id, prompt)
        cached = self._get_cached(cache_key)
        if cached:
            # Tetap update history meskipun pakai cache
            self._update_history(user_id, user_message, cached)
            logger.debug(f"Cache hit for user {user_id}")
            return cached
        
        try:
            # Panggil API
            reply = await self._call_api(prompt)
            
            # Simpan ke cache
            self._set_cache(cache_key, reply)
            
            # Update history
            self._update_history(user_id, user_message, reply)
            
            return reply
            
        except Exception as e:
            logger.error(f"AI generation failed for user {user_id}: {e}")
            
            # Fallback response
            fallback = self._get_fallback_response(
                level, arousal, 
                location.value if location else "ruang tamu",
                current_mood
            )
            
            self._update_history(user_id, user_message, fallback)
            return fallback

    def _get_fallback_response(self, 
                                level: int, 
                                arousal: float, 
                                location: str,
                                mood: Mood = None) -> str:
        """
        Fallback response jika AI error
        Memberikan respons sederhana berdasarkan level, arousal, dan lokasi
        """
        # Koleksi respons fallback
        fallbacks = {
            "default": [
                "*tersenyum*",
                "Hmm...",
                "Iya...",
                "Gitu ya...",
                "Oh...",
                "*mengangguk*"
            ],
            "horny": [
                "*napas berat* Aku... mau...",
                "*merintih* Lagi...",
                "Ah... iya...",
                "Jangan berhenti...",
                "*menggigit bibir*"
            ],
            "kamar": [
                "Di kamar... enak ya...",
                "Sepi... cuma kita berdua...",
                "Tempat tidurnya empuk...",
                "Malam-malam gini enaknya..."
            ],
            "high_level": [
                "Sayang...",
                "Cintaku...",
                "Kamu... milikku...",
                "Jangan pergi..."
            ],
            "marah": [
                "*cemberut*",
                "Kesal ah...",
                "*membuang muka*"
            ],
            "sedih": [
                "*matanya berkaca-kaca*",
                "Sedih...",
                "*menunduk*"
            ],
            "ceria": [
                "Hehe...",
                "Asik!",
                "Senang deh",
                "*tersenyum lebar*"
            ]
        }
        
        # Pilih berdasarkan mood
        if mood:
            if mood == Mood.HORNY and arousal > 0.5:
                return random.choice(fallbacks["horny"])
            elif mood == Mood.MARAH:
                return random.choice(fallbacks["marah"])
            elif mood == Mood.SEDIH:
                return random.choice(fallbacks["sedih"])
            elif mood == Mood.CERIA:
                return random.choice(fallbacks["ceria"])
        
        # Pilih berdasarkan kondisi
        if arousal > 0.7:
            return random.choice(fallbacks["horny"])
        elif "kamar" in location.lower():
            if random.random() < 0.5:
                return random.choice(fallbacks["kamar"])
        elif level > 8:
            return random.choice(fallbacks["high_level"])
        elif level > 5:
            return random.choice([
                "Sayang...",
                "Kamu...",
                "Hehe..."
            ])
        
        return random.choice(fallbacks["default"])

    def clear_history(self, user_id: int) -> bool:
        """Hapus history percakapan user"""
        if user_id in self.conversation_history:
            del self.conversation_history[user_id]
            return True
        return False

    def get_history_length(self, user_id: int) -> int:
        """Dapatkan panjang history user"""
        if user_id not in self.conversation_history:
            return 0
        return len(self.conversation_history[user_id])

    def get_cache_stats(self) -> Dict:
        """Dapatkan statistik cache"""
        total = self.cache_hits + self.cache_misses
        hit_rate = (self.cache_hits / total * 100) if total > 0 else 0
        return {
            "cache_size": len(self.cache),
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "hit_rate": f"{hit_rate:.1f}%",
            "total_calls": self.total_calls,
            "failed_calls": self.failed_calls,
            "total_tokens": self.total_tokens_used
        }

    def get_conversation_summary(self, user_id: int, max_lines: int = 5) -> str:
        """Dapatkan ringkasan percakapan untuk user"""
        if user_id not in self.conversation_history:
            return "Belum ada percakapan"
        
        history = self.conversation_history[user_id][-max_lines*2:]  # ambil beberapa pesan terakhir
        lines = []
        for msg in history[-max_lines*2:]:
            role = "👤" if msg["role"] == "user" else "🤖"
            content = truncate_text(msg["content"], 50)
            lines.append(f"{role} {content}")
        
        return "\n".join(lines)

    def export_conversation(self, user_id: int) -> str:
        """Ekspor seluruh percakapan dalam format teks"""
        if user_id not in self.conversation_history:
            return "Tidak ada percakapan"
        
        lines = ["=== EXPORT PERCAKAPAN ==="]
        for msg in self.conversation_history[user_id]:
            role = "USER" if msg["role"] == "user" else "BOT"
            time = msg.get("timestamp", "?")
            lines.append(f"[{time}] {role}: {msg['content']}")
        
        return "\n".join(lines)


print("✅ BAB 6 Selesai: AI Response Generator")
print("="*70)
# ===================== BAB 7: DATABASE MANAGER =====================
# Bagian 7.1: Connection & Transactions
# Bagian 7.2: CRUD Operations
# Bagian 7.3: Session & Stats Management

class DatabaseManager:
    """
    Manajemen database SQLite dengan connection pooling
    Thread-safe dengan context manager
    
    Fitur:
    - Connection pooling per thread
    - Context manager untuk cursor
    - Auto-commit dan rollback
    - Row factory untuk dict-like access
    - Migration support
    - Query logging
    """
    
    def __init__(self):
        self.db_path = Config.DB_PATH
        self._local = threading.local()
        self.query_count = 0
        self.query_time = 0.0
        self._init_db()
        
        logger.info(f"  • Database Manager initialized: {self.db_path}")
    
    def _get_conn(self):
        """Dapatkan koneksi database untuk thread saat ini"""
        if not hasattr(self._local, 'conn'):
            self._local.conn = sqlite3.connect(self.db_path, timeout=10)
            self._local.conn.row_factory = sqlite3.Row
            # Enable foreign keys
            self._local.conn.execute("PRAGMA foreign_keys = ON")
            # Optimize for performance
            self._local.conn.execute("PRAGMA journal_mode = WAL")
            self._local.conn.execute("PRAGMA synchronous = NORMAL")
            self._local.conn.execute("PRAGMA cache_size = 10000")
            self._local.conn.execute("PRAGMA temp_store = MEMORY")
            
        return self._local.conn
    
    @contextmanager
    def cursor(self):
        """
        Context manager untuk database cursor
        Auto-commit pada sukses, rollback pada error
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        start_time = time.time()
        
        try:
            yield cursor
            conn.commit()
            self.query_count += 1
            self.query_time += (time.time() - start_time)
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            cursor.close()
    
    def _init_db(self):
        """Inisialisasi tabel database dengan semua kolom yang diperlukan"""
        with self.cursor() as c:
            # Tabel relationships
            c.execute("""
                CREATE TABLE IF NOT EXISTS relationships (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER UNIQUE NOT NULL,
                    bot_name TEXT NOT NULL,
                    bot_role TEXT NOT NULL,
                    level INTEGER DEFAULT 1,
                    stage TEXT DEFAULT 'stranger',
                    dominance TEXT DEFAULT 'normal',
                    total_messages INTEGER DEFAULT 0,
                    total_climax INTEGER DEFAULT 0,
                    
                    -- Atribut fisik
                    hair_style TEXT,
                    height INTEGER,
                    weight INTEGER,
                    breast_size TEXT,
                    hijab BOOLEAN DEFAULT 0,
                    most_sensitive_area TEXT,
                    skin_color TEXT,
                    face_shape TEXT,
                    personality TEXT,
                    
                    -- Pakaian
                    current_clothing TEXT DEFAULT 'pakaian biasa',
                    last_clothing_change TIMESTAMP,
                    
                    -- Timestamps
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active TIMESTAMP,
                    
                    -- Metadata
                    metadata TEXT  -- JSON field untuk data tambahan
                )
            """)
            
            # Tabel conversations
            c.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    relationship_id INTEGER NOT NULL,
                    role TEXT NOT NULL,  -- 'user' atau 'assistant'
                    content TEXT NOT NULL,
                    mood TEXT,
                    arousal REAL,
                    location TEXT,
                    clothing TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (relationship_id) REFERENCES relationships(id) ON DELETE CASCADE
                )
            """)
            
            # Create index for faster queries
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_conversations_rel_time 
                ON conversations(relationship_id, timestamp)
            """)
            
            # Tabel memories (untuk long-term memory)
            c.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    relationship_id INTEGER NOT NULL,
                    memory_id TEXT UNIQUE,  -- ID dari Hippocampus
                    memory TEXT NOT NULL,
                    memory_type TEXT NOT NULL,
                    importance REAL DEFAULT 0.5,
                    emotion TEXT,
                    context TEXT,  -- JSON context
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_accessed TIMESTAMP,
                    access_count INTEGER DEFAULT 0,
                    FOREIGN KEY (relationship_id) REFERENCES relationships(id) ON DELETE CASCADE
                )
            """)
            
            # Tabel preferences
            c.execute("""
                CREATE TABLE IF NOT EXISTS preferences (
                    user_id INTEGER PRIMARY KEY,
                    romantic_score REAL DEFAULT 0,
                    vulgar_score REAL DEFAULT 0,
                    dominant_score REAL DEFAULT 0,
                    submissive_score REAL DEFAULT 0,
                    speed_score REAL DEFAULT 0,
                    total_interactions INTEGER DEFAULT 0,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Tabel sessions (untuk pause/resume)
            c.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    user_id INTEGER PRIMARY KEY,
                    relationship_id INTEGER NOT NULL,
                    paused_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    FOREIGN KEY (relationship_id) REFERENCES relationships(id) ON DELETE CASCADE
                )
            """)
            
            # Tabel stats (untuk admin analytics)
            c.execute("""
                CREATE TABLE IF NOT EXISTS stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date DATE UNIQUE,
                    new_users INTEGER DEFAULT 0,
                    active_users INTEGER DEFAULT 0,
                    total_messages INTEGER DEFAULT 0,
                    total_climax INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            logger.info("✅ Database tables initialized")

    # ========== RELATIONSHIP METHODS ==========
    
    def create_relationship(self, 
                           user_id: int, 
                           bot_name: str, 
                           bot_role: str, 
                           physical_attrs: Dict = None,
                           clothing: str = None,
                           metadata: Dict = None) -> int:
        """
        Buat hubungan baru dengan atribut fisik dan pakaian opsional
        Returns: relationship_id
        """
        with self.cursor() as c:
            # Cek apakah sudah ada
            c.execute("SELECT id FROM relationships WHERE user_id=?", (user_id,))
            existing = c.fetchone()
            if existing:
                return existing[0]
            
            # Insert data
            if physical_attrs and clothing:
                c.execute("""
                    INSERT INTO relationships 
                    (user_id, bot_name, bot_role, last_active, last_clothing_change,
                     hair_style, height, weight, breast_size, hijab, most_sensitive_area,
                     skin_color, face_shape, personality, current_clothing, metadata)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP,
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id, bot_name, bot_role,
                    physical_attrs.get('hair_style'),
                    physical_attrs.get('height'),
                    physical_attrs.get('weight'),
                    physical_attrs.get('breast_size'),
                    physical_attrs.get('hijab', 0),
                    physical_attrs.get('most_sensitive_area'),
                    physical_attrs.get('skin'),
                    physical_attrs.get('face_shape'),
                    physical_attrs.get('personality'),
                    clothing,
                    json.dumps(metadata) if metadata else None
                ))
            elif physical_attrs:
                c.execute("""
                    INSERT INTO relationships 
                    (user_id, bot_name, bot_role, last_active,
                     hair_style, height, weight, breast_size, hijab, most_sensitive_area,
                     skin_color, face_shape, personality, metadata)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP,
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id, bot_name, bot_role,
                    physical_attrs.get('hair_style'),
                    physical_attrs.get('height'),
                    physical_attrs.get('weight'),
                    physical_attrs.get('breast_size'),
                    physical_attrs.get('hijab', 0),
                    physical_attrs.get('most_sensitive_area'),
                    physical_attrs.get('skin'),
                    physical_attrs.get('face_shape'),
                    physical_attrs.get('personality'),
                    json.dumps(metadata) if metadata else None
                ))
            else:
                c.execute("""
                    INSERT INTO relationships 
                    (user_id, bot_name, bot_role, last_active, metadata)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?)
                """, (user_id, bot_name, bot_role, json.dumps(metadata) if metadata else None))
            
            return c.lastrowid

    def get_relationship(self, user_id: int) -> Optional[Dict]:
    """Dapatkan relationship berdasarkan user_id"""
    try:
        with self.cursor() as c:
            c.execute("SELECT * FROM relationships WHERE user_id=?", (user_id,))
            row = c.fetchone()
            if row:
                data = dict(row)
                print(f"✅ Data ditemukan untuk user {user_id}: {data.get('bot_name')} ({data.get('bot_role')})")
                # Parse JSON metadata
                if data.get('metadata'):
                    try:
                        data['metadata'] = json.loads(data['metadata'])
                    except:
                        data['metadata'] = {}
                return data
            else:
                print(f"ℹ️ Tidak ada data untuk user {user_id}")
                return None
    except Exception as e:
        print(f"❌ Error in get_relationship: {e}")
        return None

    def update_relationship(self, user_id: int, **kwargs) -> bool:
        """Update relationship dengan field dinamis"""
        if not kwargs:
            return False
        
        fields = []
        values = []
        for key, value in kwargs.items():
            if key in ['metadata'] and value is not None:
                # Serialize JSON fields
                value = json.dumps(value)
            fields.append(f"{key}=?")
            values.append(value)
        
        values.append(user_id)
        
        with self.cursor() as c:
            c.execute(f"""
                UPDATE relationships
                SET {', '.join(fields)}, last_active=CURRENT_TIMESTAMP
                WHERE user_id=?
            """, values)
            return c.rowcount > 0

    def update_clothing(self, user_id: int, clothing: str) -> bool:
        """Update pakaian dan timestamp perubahan"""
        with self.cursor() as c:
            c.execute("""
                UPDATE relationships
                SET current_clothing = ?, last_clothing_change = CURRENT_TIMESTAMP, last_active = CURRENT_TIMESTAMP
                WHERE user_id = ?
            """, (clothing, user_id))
            return c.rowcount > 0

    def delete_relationship(self, user_id: int) -> bool:
        """Hapus relationship dan semua data terkait"""
        with self.cursor() as c:
            # Hapus memories dulu (foreign key cascade)
            c.execute("SELECT id FROM relationships WHERE user_id=?", (user_id,))
            row = c.fetchone()
            if row:
                rel_id = row[0]
                c.execute("DELETE FROM conversations WHERE relationship_id=?", (rel_id,))
                c.execute("DELETE FROM memories WHERE relationship_id=?", (rel_id,))
                c.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
            
            # Hapus relationship
            c.execute("DELETE FROM relationships WHERE user_id=?", (user_id,))
            c.execute("DELETE FROM preferences WHERE user_id=?", (user_id,))
            
            return c.rowcount > 0

    # ========== CONVERSATION METHODS ==========
    
    def save_conversation(self, 
                         rel_id: int, 
                         role: str, 
                         content: str, 
                         mood: str = None,
                         arousal: float = None,
                         location: str = None,
                         clothing: str = None) -> int:
        """Simpan pesan percakapan"""
        with self.cursor() as c:
            c.execute("""
                INSERT INTO conversations 
                (relationship_id, role, content, mood, arousal, location, clothing)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (rel_id, role, content, mood, arousal, location, clothing))
            return c.lastrowid

    def get_conversation_history(self, 
                                rel_id: int, 
                                limit: int = 50,
                                offset: int = 0) -> List[Dict]:
        """Dapatkan history percakapan"""
        with self.cursor() as c:
            c.execute("""
                SELECT role, content, mood, arousal, location, clothing, timestamp
                FROM conversations
                WHERE relationship_id = ?
                ORDER BY timestamp ASC
                LIMIT ? OFFSET ?
            """, (rel_id, limit, offset))
            return [dict(row) for row in c.fetchall()]

    def get_recent_conversations(self, rel_id: int, hours: int = 24) -> List[Dict]:
        """Dapatkan percakapan dari beberapa jam terakhir"""
        with self.cursor() as c:
            c.execute("""
                SELECT role, content, mood, arousal, timestamp
                FROM conversations
                WHERE relationship_id = ? 
                AND timestamp > datetime('now', '-' || ? || ' hours')
                ORDER BY timestamp ASC
            """, (rel_id, hours))
            return [dict(row) for row in c.fetchall()]

    # ========== MEMORY METHODS ==========
    
    def save_memory(self, 
                   rel_id: int, 
                   memory_id: str,
                   memory: str,
                   memory_type: str,
                   importance: float,
                   emotion: str = None,
                   context: Dict = None) -> int:
        """Simpan memory ke database"""
        with self.cursor() as c:
            c.execute("""
                INSERT INTO memories 
                (relationship_id, memory_id, memory, memory_type, importance, emotion, context)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (rel_id, memory_id, memory, memory_type, importance, emotion, 
                  json.dumps(context) if context else None))
            return c.lastrowid

    def get_memories(self, 
                    rel_id: int, 
                    memory_type: str = None,
                    limit: int = 10,
                    min_importance: float = 0.0) -> List[Dict]:
        """Dapatkan memories"""
        query = """
            SELECT memory_id, memory, memory_type, importance, emotion, context, 
                   created_at, last_accessed, access_count
            FROM memories
            WHERE relationship_id = ?
        """
        params = [rel_id]
        
        if memory_type:
            query += " AND memory_type = ?"
            params.append(memory_type)
        
        if min_importance > 0:
            query += " AND importance >= ?"
            params.append(min_importance)
        
        query += " ORDER BY importance DESC, created_at DESC LIMIT ?"
        params.append(limit)
        
        with self.cursor() as c:
            c.execute(query, params)
            rows = c.fetchall()
            
            result = []
            for row in rows:
                data = dict(row)
                if data.get('context'):
                    try:
                        data['context'] = json.loads(data['context'])
                    except:
                        data['context'] = {}
                result.append(data)
            
            return result

    def update_memory_access(self, memory_id: str) -> bool:
        """Update last_accessed dan access_count untuk memory"""
        with self.cursor() as c:
            c.execute("""
                UPDATE memories
                SET last_accessed = CURRENT_TIMESTAMP, access_count = access_count + 1
                WHERE memory_id = ?
            """, (memory_id,))
            return c.rowcount > 0

    # ========== PREFERENCES METHODS ==========
    
    def update_preferences(self, user_id: int, **scores) -> bool:
        """Update preferensi user"""
        with self.cursor() as c:
            c.execute("SELECT * FROM preferences WHERE user_id=?", (user_id,))
            if c.fetchone():
                fields = []
                values = []
                for key, value in scores.items():
                    fields.append(f"{key}=?")
                    values.append(value)
                values.append(user_id)
                c.execute(f"""
                    UPDATE preferences
                    SET {', '.join(fields)}, last_updated=CURRENT_TIMESTAMP
                    WHERE user_id=?
                """, values)
            else:
                fields = ['user_id'] + list(scores.keys())
                placeholders = ['?'] * len(fields)
                values = [user_id] + list(scores.values())
                c.execute(f"""
                    INSERT INTO preferences ({', '.join(fields)})
                    VALUES ({', '.join(placeholders)})
                """, values)
            
            return True

    def get_preferences(self, user_id: int) -> Dict:
        """Dapatkan preferensi user"""
        with self.cursor() as c:
            c.execute("SELECT * FROM preferences WHERE user_id=?", (user_id,))
            row = c.fetchone()
            return dict(row) if row else {}

    # ========== SESSION METHODS ==========
    
    def save_session(self, user_id: int, rel_id: int, expire_minutes: int = 60) -> bool:
        """Simpan session yang di-pause"""
        expires_at = datetime.now() + timedelta(minutes=expire_minutes)
        
        with self.cursor() as c:
            c.execute("""
                INSERT OR REPLACE INTO sessions (user_id, relationship_id, expires_at)
                VALUES (?, ?, ?)
            """, (user_id, rel_id, expires_at.isoformat()))
            return True

    def get_session(self, user_id: int) -> Optional[Dict]:
        """Dapatkan session yang di-pause"""
        with self.cursor() as c:
            c.execute("""
                SELECT * FROM sessions 
                WHERE user_id = ? AND expires_at > datetime('now')
            """, (user_id,))
            row = c.fetchone()
            return dict(row) if row else None

    def delete_session(self, user_id: int) -> bool:
        """Hapus session"""
        with self.cursor() as c:
            c.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
            return c.rowcount > 0

    def cleanup_expired_sessions(self) -> int:
        """Hapus session yang sudah expired"""
        with self.cursor() as c:
            c.execute("DELETE FROM sessions WHERE expires_at <= datetime('now')")
            return c.rowcount

    # ========== STATS METHODS ==========
    
    def update_daily_stats(self, date: datetime.date = None) -> None:
        """Update statistik harian"""
        if date is None:
            date = datetime.now().date()
        
        # Hitung statistik
        with self.cursor() as c:
            # New users hari ini
            c.execute("""
                SELECT COUNT(*) FROM relationships 
                WHERE date(created_at) = date(?)
            """, (date.isoformat(),))
            new_users = c.fetchone()[0]
            
            # Active users hari ini
            c.execute("""
                SELECT COUNT(*) FROM relationships 
                WHERE date(last_active) = date(?)
            """, (date.isoformat(),))
            active_users = c.fetchone()[0]
            
            # Total messages hari ini
            c.execute("""
                SELECT COUNT(*) FROM conversations 
                WHERE date(timestamp) = date(?)
            """, (date.isoformat(),))
            total_messages = c.fetchone()[0]
            
            # Total climax hari ini
            c.execute("""
                SELECT COALESCE(SUM(total_climax), 0) FROM relationships 
                WHERE date(last_active) = date(?)
            """, (date.isoformat(),))
            total_climax = c.fetchone()[0]
            
            # Insert or update
            c.execute("""
                INSERT OR REPLACE INTO stats 
                (date, new_users, active_users, total_messages, total_climax)
                VALUES (?, ?, ?, ?, ?)
            """, (date.isoformat(), new_users, active_users, total_messages, total_climax))

    def get_stats(self, days: int = 7) -> Dict:
        """Dapatkan statistik untuk beberapa hari terakhir"""
        with self.cursor() as c:
            c.execute("""
                SELECT * FROM stats 
                WHERE date >= date('now', '-' || ? || ' days')
                ORDER BY date DESC
            """, (days,))
            rows = c.fetchall()
            
            stats = []
            for row in rows:
                stats.append(dict(row))
            
            # Hitung total keseluruhan
            c.execute("SELECT COUNT(*) FROM relationships")
            total_users = c.fetchone()[0]
            
            c.execute("SELECT COUNT(*) FROM conversations")
            total_messages = c.fetchone()[0]
            
            return {
                "daily": stats,
                "total_users": total_users,
                "total_messages": total_messages
            }

    def get_user_stats(self, user_id: int) -> Dict:
        """Dapatkan statistik lengkap untuk user"""
        with self.cursor() as c:
            # Data relationship
            c.execute("SELECT * FROM relationships WHERE user_id=?", (user_id,))
            rel = c.fetchone()
            if not rel:
                return {}
            
            rel_data = dict(rel)
            
            # Hitung total messages
            c.execute("""
                SELECT COUNT(*) FROM conversations 
                WHERE relationship_id=?
            """, (rel_data['id'],))
            total_messages = c.fetchone()[0]
            
            # Hitung messages per role
            c.execute("""
                SELECT role, COUNT(*) FROM conversations 
                WHERE relationship_id=? 
                GROUP BY role
            """, (rel_data['id'],))
            messages_by_role = dict(c.fetchall())
            
            # Hitung rata-rata arousal
            c.execute("""
                SELECT AVG(arousal) FROM conversations 
                WHERE relationship_id=? AND arousal IS NOT NULL
            """, (rel_data['id'],))
            avg_arousal = c.fetchone()[0]
            
            return {
                "relationship": rel_data,
                "total_messages": total_messages,
                "user_messages": messages_by_role.get('user', 0),
                "bot_messages": messages_by_role.get('assistant', 0),
                "avg_arousal": avg_arousal,
                "preferences": self.get_preferences(user_id)
            }

    # ========== UTILITY METHODS ==========
    
    def get_all_users(self, active_only: bool = False) -> List[int]:
        """Dapatkan semua user ID"""
        with self.cursor() as c:
            if active_only:
                # User yang aktif dalam 24 jam terakhir
                c.execute("""
                    SELECT user_id FROM relationships 
                    WHERE last_active > datetime('now', '-1 day')
                """)
            else:
                c.execute("SELECT user_id FROM relationships")
            
            return [row[0] for row in c.fetchall()]

    def get_total_count(self, table: str) -> int:
        """Dapatkan total record dalam tabel"""
        with self.cursor() as c:
            c.execute(f"SELECT COUNT(*) FROM {table}")
            return c.fetchone()[0]

    def vacuum(self) -> None:
        """Optimasi database (VACUUM)"""
        with self.cursor() as c:
            c.execute("VACUUM")
            logger.info("Database VACUUM completed")

    def backup(self, backup_path: str = None) -> str:
        """Backup database ke file"""
        if backup_path is None:
            backup_path = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        
        import shutil
        shutil.copy2(self.db_path, backup_path)
        logger.info(f"Database backed up to {backup_path}")
        return backup_path

    def get_db_stats(self) -> Dict:
        """Dapatkan statistik database"""
        with self.cursor() as c:
            c.execute("SELECT COUNT(*) FROM relationships")
            total_relationships = c.fetchone()[0]
            
            c.execute("SELECT COUNT(*) FROM conversations")
            total_conversations = c.fetchone()[0]
            
            c.execute("SELECT COUNT(*) FROM memories")
            total_memories = c.fetchone()[0]
            
            # Ukuran file
            size = os.path.getsize(self.db_path)
            
            return {
                "relationships": total_relationships,
                "conversations": total_conversations,
                "memories": total_memories,
                "preferences": self.get_total_count("preferences"),
                "sessions": self.get_total_count("sessions"),
                "db_size_mb": round(size / (1024 * 1024), 2),
                "query_count": self.query_count,
                "avg_query_time_ms": round((self.query_time / self.query_count * 1000) if self.query_count > 0 else 0, 2)
            }

    def close_all(self):
        """Tutup semua koneksi database"""
        if hasattr(self._local, 'conn'):
            self._local.conn.close()
            del self._local.conn
            logger.info("Database connections closed")


print("✅ BAB 7 Selesai: Database Manager")
print("="*70)
# ===================== BAB 8: MAIN BOT CLASS - CORE =====================
# Bagian 8.1: Initialization
# Bagian 8.2: Session Management
# Bagian 8.3: Stats & Utilities

class GadisUltimateV60:
    """
    Bot wanita sempurna dengan fitur premium
    Versi 60.0 dengan arsitektur modular
    
    Fitur:
    - 20+ mood dengan transisi natural
    - Sistem dominasi (dominan/submissive)
    - Leveling cepat 1-12 (45 menit)
    - Respons seksual realistis
    - Memori jangka panjang (Hippocampus)
    - Inner thoughts & proactive AI
    - Story development
    - Physical attributes
    - Dynamic clothing system
    - Location & movement
    - Couple roleplay mode
    - Admin commands
    - Database persistence
    """
    
    def __init__(self):
        """Inisialisasi semua komponen bot"""
        
        # ===== DATABASE & AI =====
        self.db = DatabaseManager()
        self.ai = AIResponseGenerator()
        self.analyzer = UserPreferenceAnalyzer()
        self.leveling = FastLevelingSystem()
        self.rate_limiter = RateLimiter(max_messages=Config.MAX_MESSAGES_PER_MINUTE)
        
        # ===== USER SESSIONS =====
        self.sessions: Dict[int, UserSession] = {}  # user_id -> UserSession
        self.paused_sessions: Dict[int, Tuple[int, datetime]] = {}  # user_id -> (rel_id, pause_time)
        
        # ===== ADVANCED MEMORY SYSTEMS =====
        self.hippocampus: Dict[int, HippocampusMemory] = {}  # user_id -> HippocampusMemory
        self.inner_thoughts: Dict[int, InnerThoughtSystem] = {}  # user_id -> InnerThoughtSystem
        self.story_developers: Dict[int, StoryDeveloper] = {}  # user_id -> StoryDeveloper
        
        # ===== LOCATION SYSTEMS =====
        self.location_systems: Dict[int, LocationSystem] = {}
        self.position_systems: Dict[int, PositionSystem] = {}
        
        # ===== COUPLE MODE =====
        self.couple_sessions: Dict[int, CoupleRoleplay] = {}
        
        # ===== PROACTIVE TRACKING =====
        self.last_proactive_time: Dict[int, datetime] = {}
        self.user_silence_tracker: Dict[int, datetime] = {}
        
        # ===== ADMIN =====
        self.admin_id = Config.ADMIN_ID
        self.is_running = True
        self.start_time = datetime.now()
        
        # ===== STATISTICS =====
        self.total_messages = 0
        self.total_commands = 0
        
        # ===== LOG STARTUP =====
        self._log_startup()
    
    def _log_startup(self):
        """Log informasi startup"""
        logger.info("="*60)
        logger.info("🚀 GADIS ULTIMATE V60.0 INITIALIZED")
        logger.info("="*60)
        logger.info(f"📂 Database: {Config.DB_PATH}")
        logger.info(f"🤖 AI Model: DeepSeek Chat")
        logger.info(f"👑 Admin ID: {self.admin_id if self.admin_id != 0 else 'Not set'}")
        logger.info(f"📊 Rate Limit: {Config.MAX_MESSAGES_PER_MINUTE} msg/min")
        logger.info(f"🎯 Target Level: {Config.TARGET_LEVEL} in {Config.LEVEL_UP_TIME} min")
        logger.info("="*60)
        
        print("\n" + "="*60)
        print("🚀 GADIS ULTIMATE V60.0 INITIALIZED")
        print("="*60)
        print(f"📂 Database: {Config.DB_PATH}")
        print(f"🤖 AI Model: DeepSeek Chat")
        print(f"👑 Admin ID: {self.admin_id if self.admin_id != 0 else 'Not set'}")
        print(f"📊 Rate Limit: {Config.MAX_MESSAGES_PER_MINUTE} msg/min")
        print("="*60 + "\n")

    # ===== GETTER METHODS =====
    
    def get_session(self, user_id: int) -> Optional[UserSession]:
        """Dapatkan atau buat session untuk user"""
        try:
            # Cek di memory dulu
            if user_id in self.sessions:
                return self.sessions.get(user_id)
        
            # Coba load dari database
            rel = self.db.get_relationship(user_id)
            if rel:
                print(f"📂 Loading session for user {user_id} from database")
                self._load_session_from_db(user_id, rel)
                return self.sessions.get(user_id)
        
            return None
        except Exception as e:
            print(f"❌ Error in get_session for user {user_id}: {e}")
            return None

    def _load_session_from_db(self, user_id: int, rel: Dict):
        """Load session dari database"""
        session = UserSession(
            user_id=user_id,
            relationship_id=rel['id'],
            bot_name=rel['bot_name'],
            bot_role=rel['bot_role'],
            level=rel['level'],
            stage=IntimacyStage(rel['stage']) if rel['stage'] else IntimacyStage.STRANGER,
            climax_count=rel['total_climax'] or 0,
            message_count=rel['total_messages'] or 0,
            created_at=datetime.fromisoformat(rel['created_at']) if rel['created_at'] else datetime.now(),
            last_active=datetime.fromisoformat(rel['last_active']) if rel['last_active'] else datetime.now()
        )
        
        # Load physical attributes
        if any([rel.get('hair_style'), rel.get('height')]):
            session.bot_physical = {
                'hair_style': rel.get('hair_style'),
                'height': rel.get('height'),
                'weight': rel.get('weight'),
                'breast_size': rel.get('breast_size'),
                'hijab': rel.get('hijab', 0),
                'most_sensitive_area': rel.get('most_sensitive_area'),
                'skin': rel.get('skin_color'),
                'face_shape': rel.get('face_shape'),
                'personality': rel.get('personality')
            }
        
        # Load clothing
        if rel.get('current_clothing'):
            session.bot_clothing = rel['current_clothing']
            if rel.get('last_clothing_change'):
                session.last_clothing_update = datetime.fromisoformat(rel['last_clothing_change'])
        
        # Load dominance
        if rel.get('dominance'):
            for level in DominanceLevel:
                if level.value == rel['dominance']:
                    session.dominance_mode = level
                    break
        
        self.sessions[user_id] = session
        logger.debug(f"Loaded session for user {user_id} from database")

    def get_hippocampus(self, user_id: int) -> HippocampusMemory:
        """Dapatkan atau buat hippocampus memory untuk user"""
        if user_id not in self.hippocampus:
            self.hippocampus[user_id] = HippocampusMemory(user_id)
        return self.hippocampus[user_id]

    def get_inner_thought(self, user_id: int) -> InnerThoughtSystem:
        """Dapatkan inner thought system untuk user"""
        if user_id not in self.inner_thoughts:
            hippocampus = self.get_hippocampus(user_id)
            self.inner_thoughts[user_id] = InnerThoughtSystem(self.ai, hippocampus, user_id)
        return self.inner_thoughts[user_id]

    def get_story_developer(self, user_id: int) -> StoryDeveloper:
        """Dapatkan story developer untuk user"""
        if user_id not in self.story_developers:
            hippocampus = self.get_hippocampus(user_id)
            self.story_developers[user_id] = StoryDeveloper(self.ai, hippocampus, user_id)
        return self.story_developers[user_id]

    def get_location_system(self, user_id: int) -> LocationSystem:
        """Dapatkan location system untuk user"""
        if user_id not in self.location_systems:
            self.location_systems[user_id] = LocationSystem()
        return self.location_systems[user_id]

    def get_position_system(self, user_id: int) -> PositionSystem:
        """Dapatkan position system untuk user"""
        if user_id not in self.position_systems:
            self.position_systems[user_id] = PositionSystem()
        return self.position_systems[user_id]

    def update_clothing(self, user_id: int, clothing: str = None):
        """Update pakaian user"""
        session = self.get_session(user_id)
        if not session:
            return
        
        if clothing:
            session.bot_clothing = clothing
        else:
            # Generate random clothing based on role and location
            location = self.get_location_system(user_id).get_current()
            session.bot_clothing = ClothingSystem.generate_clothing(
                session.bot_role,
                location.value if location else None
            )
        
        session.last_clothing_update = datetime.now()
        self.db.update_clothing(user_id, session.bot_clothing)

    # ===== SESSION CONTROL =====
    
    def create_session(self, user_id: int, bot_name: str, bot_role: str, 
                      physical_attrs: Dict, clothing: str) -> bool:
        """Buat session baru untuk user"""
        # Simpan ke database
        rel_id = self.db.create_relationship(
            user_id, bot_name, bot_role,
            physical_attrs=physical_attrs,
            clothing=clothing
        )
        
        if not rel_id:
            return False
        
        # Buat session
        session = UserSession(
            user_id=user_id,
            relationship_id=rel_id,
            bot_name=bot_name,
            bot_role=bot_role,
            bot_physical=physical_attrs,
            bot_clothing=clothing
        )
        
        self.sessions[user_id] = session
        
        # Inisialisasi leveling
        self.leveling.start_session(user_id)
        
        logger.info(f"✨ New session created: User {user_id} as {bot_name} ({bot_role})")
        return True

    def pause_session(self, user_id: int) -> bool:
        """Pause session"""
        if user_id not in self.sessions:
            return False
        
        session = self.sessions[user_id]
        
        # Save to database
        self.save_session_to_db(user_id)
        
        # Save to paused sessions
        self.paused_sessions[user_id] = (session.relationship_id, datetime.now())
        
        # Remove from active sessions
        del self.sessions[user_id]
        
        logger.info(f"⏸️ Session paused for user {user_id}")
        return True

    def unpause_session(self, user_id: int) -> bool:
        """Unpause session"""
        if user_id not in self.paused_sessions:
            return False
        
        rel_id, pause_time = self.paused_sessions[user_id]
        
        # Check if expired
        if (datetime.now() - pause_time).total_seconds() > Config.PAUSE_TIMEOUT:
            del self.paused_sessions[user_id]
            logger.info(f"⏰ Session expired for user {user_id}")
            return False
        
        # Load from database
        rel = self.db.get_relationship(user_id)
        if rel:
            self._load_session_from_db(user_id, rel)
            self.sessions[user_id].relationship_id = rel_id
        
        del self.paused_sessions[user_id]
        
        logger.info(f"▶️ Session unpaused for user {user_id}")
        return True

    def close_session(self, user_id: int, save: bool = True) -> bool:
        """Close session (soft reset - save to DB)"""
        try:
            if save and user_id in self.sessions:
                self.save_session_to_db(user_id)
        
            # Cleanup memory
            self._cleanup_user_memory(user_id)
        
            # Bersihkan juga dari aplikasi tapi simpan di DB
            if hasattr(self, 'application') and self.application:
                try:
                    # Hapus conversation dari memory tapi data tetap di DB
                    for handler in self.application.handlers.get(0, []):
                        if hasattr(handler, 'conversations'):
                            keys_to_remove = []
                            for key in handler.conversations.keys():
                                if key[0] == user_id:
                                    keys_to_remove.append(key)
                            for key in keys_to_remove:
                                del handler.conversations[key]
                except Exception as e:
                    logger.error(f"Error cleaning conversations: {e}")
        
            logger.info(f"🔒 Session closed for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Error closing session for user {user_id}: {e}")
            return False

    def end_session(self, user_id: int) -> bool:
        """End session (hard reset - delete from DB)"""
        try:
            # Delete from database
            self.db.delete_relationship(user_id)
        
            # Reset analyzer
            self.analyzer.reset_user(user_id)
        
            # Reset leveling
            self.leveling.reset(user_id)
        
            # Cleanup all memory
            self._cleanup_user_memory(user_id, hard=True)
        
            # Bersihkan juga dari aplikasi
            if hasattr(self, 'application') and self.application:
                try:
                    # Hapus conversation data jika ada
                    for handler in self.application.handlers.get(0, []):
                        if hasattr(handler, 'conversations'):
                            keys_to_remove = []
                            for key in handler.conversations.keys():
                                if key[0] == user_id:
                                    keys_to_remove.append(key)
                            for key in keys_to_remove:
                                del handler.conversations[key]
                except Exception as e:
                    logger.error(f"Error cleaning conversations: {e}")
        
            logger.info(f"💔 Session ended (hard reset) for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Error ending session for user {user_id}: {e}")
            return False

    def _cleanup_user_memory(self, user_id: int, hard: bool = False):
        """Bersihkan semua data user dari memory"""
        # Remove from sessions
        if user_id in self.sessions:
            del self.sessions[user_id]
        
        if user_id in self.paused_sessions:
            del self.paused_sessions[user_id]
        
        if not hard:
            # Untuk soft reset, data di advanced memory tetap (bisa di-load lagi)
            return
        
        # Hard reset - hapus semua
        if user_id in self.hippocampus:
            del self.hippocampus[user_id]
        if user_id in self.inner_thoughts:
            del self.inner_thoughts[user_id]
        if user_id in self.story_developers:
            del self.story_developers[user_id]
        if user_id in self.location_systems:
            del self.location_systems[user_id]
        if user_id in self.position_systems:
            del self.position_systems[user_id]
        if user_id in self.couple_sessions:
            del self.couple_sessions[user_id]
        if user_id in self.last_proactive_time:
            del self.last_proactive_time[user_id]
        if user_id in self.user_silence_tracker:
            del self.user_silence_tracker[user_id]
        
        # Reset rate limiter
        self.rate_limiter.reset_user(user_id)
        
        # Clear AI history
        self.ai.clear_history(user_id)

          # Force garbage collection
        import gc
        gc.collect()
            
        logger.info(f"🧹 Hard cleanup for user {user_id}")

    def save_session_to_db(self, user_id: int) -> bool:
        """Simpan session ke database"""
        if user_id not in self.sessions:
            return False
        
        session = self.sessions[user_id]
        
        # Update relationship
        self.db.update_relationship(
            user_id,
            level=session.level,
            stage=session.stage.value,
            total_messages=session.message_count,
            total_climax=session.climax_count,
            dominance=session.dominance_mode.value,
            current_clothing=session.bot_clothing,
            metadata={
                'location': self.location_systems.get(user_id, {}).get_current().value if user_id in self.location_systems else None,
                'position': self.position_systems.get(user_id, {}).get_current().value if user_id in self.position_systems else None
            }
        )
        
        # Update preferences
        profile = self.analyzer.get_profile(user_id)
        if profile:
            self.db.update_preferences(
                user_id,
                romantic_score=profile.get('romantis', 0),
                vulgar_score=profile.get('vulgar', 0),
                dominant_score=profile.get('dominan', 0),
                submissive_score=profile.get('submissive', 0),
                speed_score=profile.get('cepat', 0) - profile.get('lambat', 0),
                total_interactions=profile.get('total_messages', 0)
            )
        
        logger.debug(f"💾 Session saved for user {user_id}")
        return True

    # ===== STATISTICS =====
    
    def is_admin(self, user_id: int) -> bool:
        """Cek apakah user adalah admin"""
        return self.admin_id != 0 and user_id == self.admin_id

    def get_active_users_count(self) -> int:
        """Dapatkan jumlah user aktif"""
        return len(self.sessions)

    def get_paused_users_count(self) -> int:
        """Dapatkan jumlah user yang di-pause"""
        return len(self.paused_sessions)

    def get_total_users_count(self) -> int:
        """Dapatkan total user yang pernah menggunakan bot"""
        users = set()
        users.update(self.sessions.keys())
        users.update(self.paused_sessions.keys())
        users.update(self.hippocampus.keys())
        users.update(self.db.get_all_users())
        return len(users)

    def get_uptime(self) -> str:
        """Dapatkan uptime bot dalam format string"""
        delta = datetime.now() - self.start_time
        days = delta.days
        hours = delta.seconds // 3600
        minutes = (delta.seconds // 60) % 60
        seconds = delta.seconds % 60
        
        parts = []
        if days > 0:
            parts.append(f"{days} hari")
        if hours > 0:
            parts.append(f"{hours} jam")
        if minutes > 0:
            parts.append(f"{minutes} menit")
        if seconds > 0 and len(parts) == 0:
            parts.append(f"{seconds} detik")
        
        return " ".join(parts) if parts else "0 detik"

    def get_stats(self) -> Dict:
        """Dapatkan statistik bot untuk admin"""
        # Hitung total climax dari semua user
        total_climax = sum(
            session.climax_count 
            for session in self.sessions.values()
        )
        
        # Hitung total pesan
        total_messages_db = self.db.get_total_count("conversations")
        
        return {
            "uptime": self.get_uptime(),
            "active_users": self.get_active_users_count(),
            "paused_users": self.get_paused_users_count(),
            "total_users": self.get_total_users_count(),
            "total_messages": self.total_messages,
            "total_commands": self.total_commands,
            "total_climax": total_climax,
            "couple_sessions": len(self.couple_sessions),
            "db_stats": self.db.get_db_stats(),
            "cache_stats": self.ai.get_cache_stats(),
            "rate_limiter": self.rate_limiter.get_stats(),
            "memory_usage": {
                "hippocampus": len(self.hippocampus),
                "inner_thoughts": len(self.inner_thoughts),
                "story_developers": len(self.story_developers),
                "sessions": len(self.sessions)
            }
        }

    # ===== UTILITY METHODS =====
    
    async def broadcast_message(self, text: str, user_ids: List[int] = None, 
                               context: ContextTypes.DEFAULT_TYPE = None) -> Tuple[int, int]:
        """
        Kirim pesan ke semua user atau user tertentu
        Returns: (sent_count, failed_count)
        """
        if user_ids is None:
            user_ids = list(self.sessions.keys())
        
        if not context:
            return 0, len(user_ids)
        
        sent = 0
        failed = 0
        
        for user_id in user_ids:
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=text,
                    parse_mode='Markdown'
                )
                sent += 1
                await asyncio.sleep(0.05)  # Hindari flood
            except Exception as e:
                logger.error(f"Broadcast error to {user_id}: {e}")
                failed += 1
        
        return sent, failed

    def get_disclaimer(self) -> str:
        """Dapatkan teks disclaimer 18+"""
        return (
            "⚠️ **PERINGATAN DEWASA (18+)** ⚠️\n\n"
            "Bot ini mengandung konten dewasa, termasuk dialog seksual eksplisit "
            "dan simulasi hubungan intim. Dengan melanjutkan, Anda menyatakan bahwa "
            "Anda berusia 18 tahun ke atas dan setuju untuk menggunakan bot ini "
            "secara bertanggung jawab. Konten ini hanya untuk hiburan pribadi.\n\n"
            "**Fitur yang tersedia:**\n"
            "• 20+ mood dengan transisi natural\n"
            "• Sistem dominasi (dominan/submissive)\n"
            "• Leveling cepat 1-12 (45 menit)\n"
            "• Respons seksual realistis\n"
            "• Memori jangka panjang\n"
            "• Mode couple roleplay\n"
            "• Perkenalan diri fisik\n"
            "• Pakaian dinamis\n"
            "• Inner thoughts & proactive AI\n"
            "• Story development\n\n"
            "Klik 'Saya setuju' untuk melanjutkan."
        )



    def get_help_text(self, update: Update = None) -> str:
        """Dapatkan teks bantuan - tanpa Markdown"""
        help_text = (
            "📚 BANTUAN GADIS ULTIMATE V60\n\n"
            "🔹 COMMANDS UTAMA\n"
            "/start - Mulai hubungan baru\n"
            "/status - Lihat status lengkap\n"
            "/dominant [level] - Set mode dominan\n"
            "/pause - Jeda sesi\n"
            "/unpause - Lanjutkan sesi\n"
            "/close - Tutup sesi (simpan memori)\n"
            "/end - Akhiri hubungan & hapus data\n"
            "/help - Tampilkan bantuan\n\n"
            "🔹 LEVEL DOMINAN\n"
            "• normal - Mode biasa\n"
            "• dominan - Mode dominan\n"
            "• sangat dominan - Mode sangat dominan\n"
            "• agresif - Mode agresif\n"
            "• patuh - Mode patuh\n\n"
            "🔹 TIPS CHAT\n"
            "• Gunakan *tindakan* seperti *peluk*, *cium*\n"
            "• Sebut area sensitif sesuai perkenalan bot\n"
            "• Bilang 'kamu yang atur' untuk mode dominan\n"
            "• Bilang 'aku yang atur' untuk mode submissive\n"
            "• Level 7+ bot akan lebih vulgar dan inisiatif\n\n"
            "🔹 TARGET LEVEL\n"
            "Level 1-12 dalam 45 menit / 45 pesan!"
        )
    
        if update and self.is_admin(update.effective_user.id):
            help_text += "\n\n🔐 ADMIN COMMANDS\n"
            help_text += "/admin - Menu admin\n"
            help_text += "/stats - Statistik bot\n"
            help_text += "/db_stats - Statistik database\n"
            help_text += "/reload - Reload konfigurasi\n"
            help_text += "/list_users - Daftar user\n"
            help_text += "/get_user <id> - Detail user\n"
            help_text += "/force_reset <user_id> - Reset user\n"
            help_text += "/backup_db - Backup database\n"
            help_text += "/vacuum - Optimasi database\n"
            help_text += "/memory_stats <user_id> - Statistik memori"
    
        return help_text

    def log_command(self, command: str, user_id: int, username: str):
        """Log penggunaan command"""
        self.total_commands += 1
        logger.info(f"📝 Command /{command} by {username} (ID: {user_id})")

    def track_silence(self, user_id: int):
        """Track kapan terakhir user bicara"""
        self.user_silence_tracker[user_id] = datetime.now()

    def get_silence_duration(self, user_id: int) -> float:
        """Dapatkan durasi diam user dalam detik"""
        if user_id in self.user_silence_tracker:
            return (datetime.now() - self.user_silence_tracker[user_id]).total_seconds()
        return 0

# ===================== BAB 9: MAIN BOT CLASS - COMMANDS =====================
# Bagian 9.1: Start & Role Selection

    # ===== START COMMAND =====
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Memulai hubungan baru dengan bot"""
        user_id = update.effective_user.id
        username = update.effective_user.username or update.effective_user.first_name

        self.log_command('start', user_id, username)
        print(f"🚀🚀🚀 START COMMAND from user {user_id} 🚀🚀🚀")
        print(f"📝 Username: {username}")

        # Bersihkan context
        if context.user_data:
            context.user_data.clear()
            print(f"🧹 Context cleared for user {user_id}")

        # Cek apakah sudah ada sesi aktif
        if user_id in self.sessions:
            print(f"⚠️ User {user_id} sudah memiliki sesi aktif")
            await update.message.reply_text(
                "Kamu sudah memiliki sesi aktif. Ketik /close untuk menutup sesi atau /pause untuk jeda."
            )
            return ConversationHandler.END

        # Cek apakah ada sesi di-pause
        if user_id in self.paused_sessions:
            print(f"⏸️ User {user_id} memiliki sesi di-pause")
            keyboard = [
                [InlineKeyboardButton("✅ Lanjutkan", callback_data="unpause")],
                [InlineKeyboardButton("🆕 Mulai Baru", callback_data="new")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "⚠️ Ada sesi yang di-pause. Pilih:", 
                reply_markup=reply_markup
            )
            print(f"✅ Pilihan pause terkirim, return SELECTING_ROLE")
            return Constants.SELECTING_ROLE

        # 🔴 CEK DATABASE - Pastikan ini berjalan
        print(f"🔍 Mengecek database untuk user {user_id}")
        try:
            rel = self.db.get_relationship(user_id)
            print(f"📊 Hasil query database: {rel}")
        
            if rel:
                print(f"📂 Ditemukan data hubungan di database untuk user {user_id}")
                print(f"📋 Data: {rel}")
                keyboard = [
                    [InlineKeyboardButton("✅ Lanjutkan", callback_data="unpause")],
                    [InlineKeyboardButton("🆕 Mulai Baru", callback_data="new")],
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    "⚠️ Ada sesi yang tersimpan. Pilih:", 
                    reply_markup=reply_markup
                )
                print(f"✅ Pilihan tersimpan terkirim, return SELECTING_ROLE")
                return Constants.SELECTING_ROLE
            else:
                print(f"📂 Tidak ada data hubungan di database untuk user {user_id}")
        except Exception as e:
            print(f"❌ Error saat cek database: {e}")

        # Tampilkan disclaimer 18+
        print(f"📤 Mengirim disclaimer ke user {user_id}")
        disclaimer = self.get_disclaimer()
        keyboard = [[InlineKeyboardButton("✅ Saya setuju (18+)", callback_data="agree_18")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            disclaimer, 
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        print(f"✅ Disclaimer terkirim, return SELECTING_ROLE")
        return Constants.SELECTING_ROLE

    # ===== AGREE 18 CALLBACK =====
    
    async def agree_18_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Callback setelah user setuju disclaimer"""
        print("🔥🔥🔥 AGREE_18_CALLBACK DIPANGGIL!")
        
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        print(f"📝 User {user_id} agreed to 18+ disclaimer")
        
        # Tampilkan pilihan role dengan deskripsi
        keyboard = [
            [InlineKeyboardButton("👨‍👩‍👧‍👦 Ipar", callback_data="role_ipar")],
            [InlineKeyboardButton("💼 Teman Kantor", callback_data="role_teman_kantor")],
            [InlineKeyboardButton("💃 Janda", callback_data="role_janda")],
            [InlineKeyboardButton("🦹 Pelakor", callback_data="role_pelakor")],
            [InlineKeyboardButton("💍 Istri Orang", callback_data="role_istri_orang")],
            [InlineKeyboardButton("🌿 PDKT", callback_data="role_pdkt")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "✨ **Pilih Role untukku**\n\n"
            "Setiap role punya karakter dan gaya bicara berbeda:\n"
            "• 👨‍👩‍👧‍👦 **Ipar** - Saudara ipar yang nakal\n"
            "• 💼 **Teman Kantor** - Rekan kerja yang mesra\n"
            "• 💃 **Janda** - Janda muda yang genit\n"
            "• 🦹 **Pelakor** - Perebut laki orang\n"
            "• 💍 **Istri Orang** - Istri orang lain\n"
            "• 🌿 **PDKT** - Sedang pendekatan\n\n"
            "Pilih salah satu:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return Constants.SELECTING_ROLE

    # ===== ROLE CALLBACK =====
    
    async def role_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Callback setelah user memilih role"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        role = query.data.replace("role_", "")
        
        print(f"🔥🔥🔥 ROLE_CALLBACK DIPANGGIL! User: {user_id}, Role: {role}")
        
        # Pilih nama random sesuai role
        name = random.choice(Constants.ROLE_NAMES.get(role, ["Aurora"]))
        
        # Generate atribut fisik
        physical = PhysicalAttributesGenerator.generate(role)
        
        # Generate pakaian awal
        initial_clothing = ClothingSystem.generate_clothing(role)
        
        # Buat session
        success = self.create_session(user_id, name, role, physical, initial_clothing)
        
        if not success:
            print(f"❌ Gagal membuat session untuk user {user_id}")
            await query.edit_message_text("❌ Gagal membuat session. Coba lagi.")
            return ConversationHandler.END
        
        # Intro dengan deskripsi fisik
        intro = PhysicalAttributesGenerator.format_intro(name, role, physical)
        
        # Tambah info pakaian awal
        intro += f"\n\n💃 *Hari ini aku pakai {initial_clothing}*"
        
        await query.edit_message_text(intro, parse_mode='Markdown')
        
        logger.info(f"✨ New relationship: User {user_id} as {name} ({role})")
        print(f"✅ Session created for user {user_id} as {name} ({role})")
        
        return Constants.ACTIVE_SESSION

    # ===== START PAUSE CALLBACK =====
    
    async def start_pause_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Callback untuk memilih lanjutkan atau mulai baru saat ada session tersimpan"""
        print(f"🔥 START_PAUSE_CALLBACK DIPANGGIL!")
        
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        if query.data == "unpause":
            print(f"📝 User {user_id} memilih unpause")
            
            # Coba unpause dari paused_sessions terlebih dahulu
            if self.unpause_session(user_id):
                session = self.get_session(user_id)
                clothing = session.bot_clothing if session else "pakaian biasa"
                await query.edit_message_text(
                    f"▶️ **Sesi dilanjutkan!**\n\n"
                    f"Aku masih pakai *{clothing}*\n\n"
                    f"Kangen... 💕",
                    parse_mode='Markdown'
                )
                return Constants.ACTIVE_SESSION
            else:
                # Jika tidak ada di paused_sessions, coba muat dari database
                session = self.get_session(user_id)  # Akan memuat dari database jika ada
                if session:
                    # Hapus dari paused_sessions jika ada (untuk jaga-jaga)
                    if user_id in self.paused_sessions:
                        del self.paused_sessions[user_id]
                    clothing = session.bot_clothing
                    await query.edit_message_text(
                        f"▶️ **Sesi dilanjutkan!**\n\n"
                        f"Aku masih pakai *{clothing}*\n\n"
                        f"Kangen... 💕",
                        parse_mode='Markdown'
                    )
                    return Constants.ACTIVE_SESSION
                else:
                    print(f"❌ Tidak ada sesi untuk user {user_id}")
                    await query.edit_message_text("❌ Tidak ada sesi yang dapat dilanjutkan.")
                    return ConversationHandler.END

        elif query.data == "new":
            print(f"📝 User {user_id} memulai baru")
            
            # Mulai baru - hapus semua data
            self.end_session(user_id)  # hard reset, hapus dari memory dan database
            
            # Tampilkan disclaimer
            disclaimer = self.get_disclaimer()
            keyboard = [[InlineKeyboardButton("✅ Saya setuju (18+)", callback_data="agree_18")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                disclaimer, 
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            return Constants.SELECTING_ROLE

        return ConversationHandler.END

    # ===== ROLE-SPECIFIC CALLBACKS =====
    
    async def role_ipar_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        print(f"🔥 role_ipar_callback dipanggil")
        return await self.role_callback(update, context)

    async def role_teman_kantor_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        print(f"🔥 role_teman_kantor_callback dipanggil")
        return await self.role_callback(update, context)

    async def role_janda_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        print(f"🔥 role_janda_callback dipanggil")
        return await self.role_callback(update, context)

    async def role_pelakor_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        print(f"🔥 role_pelakor_callback dipanggil")
        return await self.role_callback(update, context)

    async def role_istri_orang_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        print(f"🔥 role_istri_orang_callback dipanggil")
        return await self.role_callback(update, context)

    async def role_pdkt_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        print(f"🔥 role_pdkt_callback dipanggil")
        return await self.role_callback(update, context)

    # ===== STATUS COMMAND =====
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Lihat status lengkap hubungan saat ini"""
        user_id = update.effective_user.id
        username = update.effective_user.username or update.effective_user.first_name
    
        self.log_command('status', user_id, username)
        print(f"📊 STATUS COMMAND dipanggil oleh user {user_id}")
    
        try:
            # Cek apakah user memiliki sesi aktif
            session = self.get_session(user_id)
            if not session:
                print(f"⚠️ Session tidak ditemukan untuk user {user_id}")
                await update.message.reply_text(
                    "❌ Belum ada hubungan. /start dulu ya!"
                )
                return
        
            print(f"✅ Session ditemukan: level {session.level}")
        
            # Dapatkan semua data
            level_stats = self.leveling.get_user_stats(user_id)
            profile = self.analyzer.get_profile(user_id)
        
            # Cek location system
            try:
                location_system = self.get_location_system(user_id)
                loc_info = location_system.get_current_info()
            except Exception as e:
                print(f"⚠️ Error getting location: {e}")
                loc_info = {"name": "ruang tamu", "emoji": "🏠", "description": "", "time_here": 0}
        
            # Cek position system
            try:
                position_system = self.get_position_system(user_id)
                pos_info = position_system.get_current_info()
            except Exception as e:
                print(f"⚠️ Error getting position: {e}")
                pos_info = {"name": "duduk", "emoji": "🧘", "action": "duduk"}
        
            # Hitung progress
            progress_bar = self.leveling.get_progress_bar(user_id, 15)
            remaining = self.leveling.get_estimated_time(user_id)
        
            # Format physical description
            hijab_str = "Berhijab" if session.bot_physical.get('hijab') else "Tidak berhijab"
        
            # Handle missing physical attributes
            hair = session.bot_physical.get('hair_style', '?')
            height = session.bot_physical.get('height', '?')
            weight = session.bot_physical.get('weight', '?')
            breast = session.bot_physical.get('breast_desc', session.bot_physical.get('breast_size', '?'))
            sensitive = session.bot_physical.get('most_sensitive_area', '?')
        
            physical_text = (
                f"📏 **Fisikku:**\n"
                f"• Rambut: {hair}\n"
                f"• Tinggi: {height} cm\n"
                f"• Berat: {weight} kg\n"
                f"• Dada: {breast}\n"
                f"• {hijab_str}\n"
                f"• Area sensitif: **{sensitive}**\n"
                f"• Pakaian: **{session.bot_clothing}**\n\n"
            )
        
            # Format status
            status = (
                f"💕 **{session.bot_name} & Kamu**\n\n"
                f"📊 **PROGRESS HUBUNGAN**\n"
                f"Level: {session.level}/12\n"
                f"Tahap: {session.stage.value}\n"
                f"Progress: {progress_bar}\n"
                f"Estimasi sisa: {remaining} menit\n"
                f"Total pesan: {session.message_count}\n\n"
                f"{physical_text}"
                f"📍 **LOKASI & POSISI**\n"
                f"{loc_info['emoji']} {loc_info['name']} - {loc_info['description']}\n"
                f"{pos_info['emoji']} {pos_info['action']}\n"
                f"Di sini selama: {TimeFormatter.seconds_to_text(loc_info['time_here'])}\n\n"
                f"🔥 **KONDISI FISIK**\n"
                f"Arousal: {session.arousal:.1f}\n"
                f"Wetness: {session.wetness:.1f}\n"
                f"Sentuhan sensitif: {session.touch_count}x\n"
                f"Orgasme: {session.climax_count}x\n"
                f"Sentuhan terakhir: {session.last_touch or '-'}\n\n"
                f"👑 **MODE DOMINASI**\n"
                f"Mode: {session.dominance_mode.value}\n\n"
            )
        
            # Tambah analisis preferensi
            if profile:
                status += self.analyzer.get_summary(user_id)
        
            print(f"✅ Status berhasil dibuat untuk user {user_id}")
        
            # Kirim dengan parse_mode Markdown (teks sudah aman)
            await update.message.reply_text(status, parse_mode='Markdown')
        
        except Exception as e:
            print(f"❌ ERROR di status_command: {e}")
            import traceback
            traceback.print_exc()
            await update.message.reply_text(
                "😔 Maaf, terjadi error saat mengambil status. Coba lagi ya!"
            )

    # ===== DOMINANT COMMAND =====
    
    async def dominant_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set mode dominan manual"""
        user_id = update.effective_user.id
        username = update.effective_user.username or update.effective_user.first_name
        
        self.log_command('dominant', user_id, username)
        
        # Cek apakah user memiliki sesi aktif
        session = self.get_session(user_id)
        if not session:
            await update.message.reply_text("❌ Belum ada hubungan. /start dulu!")
            return
        
        args = context.args
        
        # Jika tidak ada argumen, tampilkan mode saat ini
        if not args:
            await update.message.reply_text(
                f"👑 **Mode Dominan Saat Ini**\n"
                f"{session.dominance_mode.value}\n\n"
                f"**Pilihan Level:**\n"
                f"• `/dominant normal` - Mode biasa\n"
                f"• `/dominant dominan` - Mode dominan\n"
                f"• `/dominant sangat dominan` - Mode sangat dominan\n"
                f"• `/dominant agresif` - Mode agresif\n"
                f"• `/dominant patuh` - Mode patuh\n\n"
                f"Contoh: `/dominant dominan`"
            )
            return
        
        # Parse level
        level = " ".join(args).lower()
        level_map = {
            "normal": DominanceLevel.NORMAL,
            "dominan": DominanceLevel.DOMINANT,
            "sangat dominan": DominanceLevel.VERY_DOMINANT,
            "agresif": DominanceLevel.AGGRESSIVE,
            "patuh": DominanceLevel.SUBMISSIVE
        }
        
        if level in level_map:
            session.dominance_mode = level_map[level]
            self.db.update_relationship(user_id, dominance=session.dominance_mode.value)
            
            responses = {
                DominanceLevel.NORMAL: "😊 Baiklah, aku akan bersikap normal.",
                DominanceLevel.DOMINANT: "👑 Sekarang aku yang pegang kendali. Ikut aku!",
                DominanceLevel.VERY_DOMINANT: "🔥 Kamu sudah milikku sepenuhnya! Jangan banyak gerak!",
                DominanceLevel.AGGRESSIVE: "💢 Siap-siap! Aku akan kasar hari ini!",
                DominanceLevel.SUBMISSIVE: "🥺 Iya... aku patuh sama kamu."
            }
            
            await update.message.reply_text(
                f"{responses.get(session.dominance_mode, '✅ Mode diubah')}"
            )
        else:
            await update.message.reply_text(
                "❌ Level tidak valid. Gunakan: normal, dominan, sangat dominan, agresif, atau patuh"
            )

    # ===== PAUSE COMMAND =====
    
    async def pause_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Pause sesi sementara"""
        user_id = update.effective_user.id
        username = update.effective_user.username or update.effective_user.first_name
        
        self.log_command('pause', user_id, username)
        
        # Cek apakah user memiliki sesi aktif
        if user_id not in self.sessions:
            await update.message.reply_text("❌ Tidak ada sesi aktif.")
            return
        
        if self.pause_session(user_id):
            await update.message.reply_text(
                f"⏸️ **Sesi di-pause**\n"
                f"Ketik /unpause untuk melanjutkan.\n"
                f"Sesi akan expired dalam {Config.PAUSE_TIMEOUT//60} menit.\n\n"
                f"*Aku akan menunggumu kembali...* 💕"
            )
        else:
            await update.message.reply_text("❌ Gagal mem-pause sesi.")

    # ===== UNPAUSE COMMAND =====
    
    async def unpause_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Lanjutkan sesi yang di-pause"""
        user_id = update.effective_user.id
        username = update.effective_user.username or update.effective_user.first_name
        
        self.log_command('unpause', user_id, username)
        
        if self.unpause_session(user_id):
            session = self.get_session(user_id)
            clothing = session.bot_clothing if session else "pakaian biasa"
            
            await update.message.reply_text(
                f"▶️ **Sesi dilanjutkan!**\n\n"
                f"Aku masih pakai *{clothing}*\n\n"
                f"Kangen... 💕"
            )
        else:
            await update.message.reply_text(
                "❌ Tidak ada sesi di-pause atau sesi sudah expired."
            )

    # ===== CLOSE COMMAND =====
    
    async def close_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Menutup sesi tapi menyimpan memori di database"""
        user_id = update.effective_user.id
        username = update.effective_user.username or update.effective_user.first_name
    
        self.log_command('close', user_id, username)
        print(f"🔒 CLOSE COMMAND from user {user_id}")
    
        # Cek apakah user memiliki sesi aktif
        if user_id not in self.sessions and user_id not in self.paused_sessions:
            await update.message.reply_text("❌ Tidak ada sesi aktif.")
            return
    
        # Konfirmasi close
        keyboard = [
            [InlineKeyboardButton("✅ Ya, tutup", callback_data="close_yes")],
            [InlineKeyboardButton("❌ Tidak", callback_data="close_no")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
    
        # Dapatkan statistik untuk ditampilkan
        session = self.get_session(user_id) if user_id in self.sessions else None
        level = session.level if session else 1
        climax = session.climax_count if session else 0
    
        await update.message.reply_text(
            f"⚠️ **Tutup Sesi?** ⚠️\n\n"
            f"Yakin ingin menutup sesi?\n\n"
            f"📊 **Statistik sementara:**\n"
            f"• Level: {level}/12\n"
            f"• Orgasme: {climax}x\n\n"
            f"**Yang akan terjadi:**\n"
            f"✅ Semua percakapan akan **disimpan** di database\n"
            f"✅ Kamu bisa memulai role baru nanti dengan /start\n"
            f"❌ Sesi saat ini akan berakhir\n\n"
            f"Lanjutkan?",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return Constants.CONFIRM_CLOSE

    async def close_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Callback untuk konfirmasi close"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
    
        if query.data == "close_no":
            await query.edit_message_text("💕 Lanjutkan ngobrol...")
            return ConversationHandler.END
    
        print(f"🔒 CLOSE_CONFIRM for user {user_id}")
    
        # Dapatkan statistik sebelum close
        session = self.get_session(user_id)
        level = session.level if session else 1
        climax = session.climax_count if session else 0
        name = session.bot_name if session else "Aku"
    
        # 🔴 PASTIKAN DATA DISIMPAN KE DATABASE
        if session:
            print(f"💾 Menyimpan session user {user_id} ke database")
            self.save_session_to_db(user_id)
            print(f"✅ Session tersimpan")
    
        # Close session (soft reset)
        self.close_session(user_id, save=False)  # save=False karena sudah disimpan
    
        # Verifikasi data tersimpan
        rel = self.db.get_relationship(user_id)
        if rel:
            print(f"✅ Verifikasi: Data user {user_id} tersimpan di database")
        else:
            print(f"❌ Verifikasi: Data user {user_id} TIDAK tersimpan di database")
    
        await query.edit_message_text(
            f"🔒 **Sesi ditutup**\n\n"
            f"Terima kasih sudah ngobrol dengan {name}.\n"
            f"Semua kenangan kita telah kusimpan rapi.\n\n"
            f"Level {level}/12 yang kita capai akan selalu kuingat.\n\n"
            f"Ketik /start kapan saja untuk bertemu lagi... 💕",
            parse_mode='Markdown'
        )
    
        logger.info(f"User {user_id} closed session (level {level})")
        return ConversationHandler.END

    # ===== END COMMAND =====
    
    async def end_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Mengakhiri hubungan dan menghapus semua data (hard reset)"""
        user_id = update.effective_user.id
        username = update.effective_user.username or update.effective_user.first_name
        
        self.log_command('end', user_id, username)
        
        # Cek apakah user memiliki sesi aktif
        if user_id not in self.sessions:
            await update.message.reply_text("❌ Tidak ada hubungan aktif.")
            return
        
        # Konfirmasi end
        keyboard = [
            [InlineKeyboardButton("💔 Ya, akhiri", callback_data="end_yes")],
            [InlineKeyboardButton("💕 Tidak", callback_data="end_no")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Dapatkan statistik untuk ditampilkan
        session = self.get_session(user_id)
        name = session.bot_name if session else "Aku"
        level = session.level if session else 1
        climax = session.climax_count if session else 0
        touch = session.touch_count if session else 0
        
        await update.message.reply_text(
            f"⚠️ **PERINGATAN!** ⚠️\n\n"
            f"Yakin ingin **mengakhiri hubungan** dengan {name}?\n\n"
            f"📊 **Statistik akhir yang akan hilang:**\n"
            f"• Level: {level}/12\n"
            f"• Orgasme bersama: {climax}x\n"
            f"• Total sentuhan: {touch}x\n"
            f"• {session.message_count} pesan\n\n"
            f"💔 **Yang akan terjadi:**\n"
            f"❌ **Semua data akan dihapus permanen**\n"
            f"❌ Riwayat percakapan akan hilang selamanya\n"
            f"❌ Tidak ada undo!\n\n"
            f"**APAKAH KAMU YAKIN?**",
            reply_markup=reply_markup
        )
        return Constants.CONFIRM_END

    async def end_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Callback untuk konfirmasi end"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "end_no":
            await query.edit_message_text("💕 Lanjutkan...")
            return ConversationHandler.END
        
        user_id = query.from_user.id
        
        # Dapatkan statistik sebelum dihapus
        session = self.get_session(user_id)
        stats = {
            "level": session.level,
            "orgasm": session.climax_count,
            "touch": session.touch_count,
            "messages": session.message_count,
            "duration": self.leveling.get_session_duration(user_id),
            "role": session.bot_role,
            "name": session.bot_name
        }
        
        # End session (hard reset)
        self.end_session(user_id)
        
        await query.edit_message_text(
            f"💔 **Hubungan Berakhir** 💔\n\n"
            f"Perjalananmu dengan **{stats['name']}** telah usai.\n\n"
            f"📊 **Statistik akhir:**\n"
            f"• Role: {stats['role']}\n"
            f"• Level akhir: {stats['level']}/12\n"
            f"• Orgasme bersama: {stats['orgasm']}x\n"
            f"• Total sentuhan: {stats['touch']}x\n"
            f"• Total pesan: {stats['messages']}\n"
            f"• Durasi: {stats['duration']} menit\n\n"
            f"✨ **Semua data telah dihapus permanen** ✨\n\n"
            f"Ketik /start untuk memulai hubungan baru dengan kenangan baru..."
        )
        
        logger.info(f"User {user_id} ended relationship - Level {stats['level']}")
        return ConversationHandler.END

    # ===== CANCEL COMMAND =====
    
    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Membatalkan percakapan (untuk ConversationHandler)"""
        user_id = update.effective_user.id
        username = update.effective_user.username or update.effective_user.first_name
        
        self.log_command('cancel', user_id, username)
        
        await update.message.reply_text(
            "❌ Dibataikan. Ketik /start untuk memulai."
        )
        return ConversationHandler.END

    # ===== HELP COMMAND =====
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Menampilkan bantuan lengkap"""
        user_id = update.effective_user.id
        username = update.effective_user.username or update.effective_user.first_name
    
        self.log_command('help', user_id, username)
        print(f"📚 HELP COMMAND from user {user_id}")
    
        help_text = self.get_help_text(update)
    
        # Kirim tanpa parse_mode
        await update.message.reply_text(help_text)

    async def admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Menu admin - menampilkan semua command admin"""
        user_id = update.effective_user.id
        username = update.effective_user.username or update.effective_user.first_name
    
        self.log_command('admin', user_id, username)
        print(f"🔐 ADMIN COMMAND from user {user_id}")
    
        if not self.is_admin(user_id):
            await update.message.reply_text("⛔ Anda bukan admin.")
            return
    
        stats = self.get_stats()
    
        text = (
            "🔐 MENU ADMIN\n\n"
            "📋 Command Admin:\n"
            "/admin - Tampilkan menu ini\n"
            "/stats - Lihat statistik bot\n"
            "/db_stats - Lihat statistik database\n"
            "/reload - Reload konfigurasi dari .env\n"
            "/list_users - Lihat daftar user aktif\n"
            "/get_user <user_id> - Lihat detail user\n"
            "/force_reset <user_id> - Reset paksa user\n"
            "/backup_db - Backup database\n"
            "/vacuum - Optimasi database\n"
            "/memory_stats <user_id> - Statistik memori\n\n"
            "📊 Status Bot:\n"
            f"• Uptime: {stats['uptime']}\n"
            f"• User aktif: {stats['active_users']}\n"
            f"• Total user: {stats['total_users']}\n"
            f"• Total pesan: {stats['total_messages']}"
        )
    
        # Kirim tanpa parse_mode
        await update.message.reply_text(text)
     
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Tampilkan statistik lengkap bot (untuk admin)"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            await update.message.reply_text("⛔ Anda bukan admin.")
            return
        
        stats = self.get_stats()
        
        text = (
            f"📊 **STATISTIK BOT**\n\n"
            f"⏱️ Uptime: {stats['uptime']}\n"
            f"👥 **User:**\n"
            f"• Aktif: {stats['active_users']}\n"
            f"• Pause: {stats['paused_users']}\n"
            f"• Total: {stats['total_users']}\n\n"
            f"💬 **Pesan:**\n"
            f"• Total pesan: {stats['total_messages']}\n"
            f"• Total command: {stats['total_commands']}\n"
            f"• Total climax: {stats['total_climax']}\n\n"
            f"👫 **Couple Mode:** {stats['couple_sessions']} sesi aktif\n\n"
            f"📦 **Memory Usage:**\n"
            f"• Hippocampus: {stats['memory_usage']['hippocampus']}\n"
            f"• Inner Thoughts: {stats['memory_usage']['inner_thoughts']}\n"
            f"• Story Developers: {stats['memory_usage']['story_developers']}\n\n"
            f"⚡ **Rate Limiter:**\n"
            f"• Active users: {stats['rate_limiter']['active_now']}\n"
            f"• Blocked: {stats['rate_limiter']['blocked_now']}\n"
            f"• Warnings: {stats['rate_limiter']['warnings']}"
        )
        
        await update.message.reply_text(text, parse_mode='Markdown')
    
    async def db_stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Tampilkan statistik database"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            await update.message.reply_text("⛔ Anda bukan admin.")
            return
        
        db_stats = self.db.get_db_stats()
        
        text = (
            f"📂 **STATISTIK DATABASE**\n\n"
            f"• Relationships: {db_stats['relationships']}\n"
            f"• Conversations: {db_stats['conversations']}\n"
            f"• Memories: {db_stats['memories']}\n"
            f"• Preferences: {db_stats['preferences']}\n"
            f"• Sessions: {db_stats['sessions']}\n\n"
            f"📏 Ukuran file: {db_stats['db_size_mb']} MB\n"
            f"📊 Query count: {db_stats['query_count']}\n"
            f"⏱️ Avg query time: {db_stats['avg_query_time_ms']} ms"
        )
        
        await update.message.reply_text(text, parse_mode='Markdown')
    
    async def reload_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Reload konfigurasi dari .env"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            await update.message.reply_text("⛔ Anda bukan admin.")
            return
        
        try:
            # Reload .env
            load_dotenv(override=True)
            
            # Update config values
            Config.ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
            Config.AI_TEMPERATURE = float(os.getenv("AI_TEMPERATURE", "0.9"))
            Config.AI_MAX_TOKENS = int(os.getenv("AI_MAX_TOKENS", "300"))
            Config.AI_TIMEOUT = int(os.getenv("AI_TIMEOUT", "30"))
            Config.MAX_MESSAGES_PER_MINUTE = int(os.getenv("MAX_MESSAGES_PER_MINUTE", "10"))
            
            # Update admin ID
            self.admin_id = Config.ADMIN_ID
            
            await update.message.reply_text(
                f"✅ **Konfigurasi direload**\n\n"
                f"• Admin ID: {self.admin_id}\n"
                f"• AI Temperature: {Config.AI_TEMPERATURE}\n"
                f"• Max Messages/min: {Config.MAX_MESSAGES_PER_MINUTE}"
            )
            
            logger.info(f"Admin {user_id} reloaded configuration")
            
        except Exception as e:
            await update.message.reply_text(f"❌ Gagal reload: {str(e)}")
            logger.error(f"Reload failed: {e}")
    
    async def list_users_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Lihat daftar user aktif"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            await update.message.reply_text("⛔ Anda bukan admin.")
            return
        
        active_users = list(self.sessions.keys())
        paused_users = list(self.paused_sessions.keys())
        
        text = "**📋 DAFTAR USER**\n\n"
        
        if active_users:
            text += "**✅ Aktif:**\n"
            for uid in active_users[:10]:  # Batasi 10 user
                session = self.sessions.get(uid)
                if session:
                    text += f"• `{uid}` - {session.bot_name} ({session.bot_role}) Lv{session.level}\n"
                else:
                    text += f"• `{uid}`\n"
            if len(active_users) > 10:
                text += f"  ... dan {len(active_users) - 10} lainnya\n"
        
        if paused_users:
            text += "\n**⏸️ Paused:**\n"
            for uid in paused_users[:5]:
                text += f"• `{uid}`\n"
        
        if not active_users and not paused_users:
            text += "Tidak ada user aktif.\n"
        
        text += f"\nTotal: {len(active_users)} aktif, {len(paused_users)} pause"
        
        await update.message.reply_text(text, parse_mode='Markdown')
    
    async def get_user_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Lihat detail user tertentu"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            await update.message.reply_text("⛔ Anda bukan admin.")
            return
        
        if not context.args:
            await update.message.reply_text("Gunakan: /get_user <user_id>")
            return
        
        try:
            target_id = int(context.args[0])
        except:
            await update.message.reply_text("❌ User ID harus angka")
            return
        
        # Cek apakah user ada di memory
        session = self.get_session(target_id)
        if not session:
            # Coba dari database
            rel = self.db.get_relationship(target_id)
            if not rel:
                await update.message.reply_text(f"❌ User {target_id} tidak ditemukan")
                return
            # Load sementara
            self._load_session_from_db(target_id, rel)
            session = self.get_session(target_id)
        
        # Dapatkan statistik
        text = (
            f"**📋 DETAIL USER `{target_id}`**\n\n"
            f"**Identitas:**\n"
            f"• Nama: {session.bot_name}\n"
            f"• Role: {session.bot_role}\n"
            f"• Level: {session.level}/12 ({session.stage.value})\n"
            f"• Total pesan: {session.message_count}\n"
            f"• Orgasme: {session.climax_count}\n\n"
            f"**Fisik:**\n"
            f"• Rambut: {session.bot_physical.get('hair_style', '-')}\n"
            f"• Tinggi: {session.bot_physical.get('height', '-')} cm\n"
            f"• Berat: {session.bot_physical.get('weight', '-')} kg\n"
            f"• Dada: {session.bot_physical.get('breast_desc', '-')}\n"
            f"• Hijab: {'Ya' if session.bot_physical.get('hijab') else 'Tidak'}\n"
            f"• Area sensitif: {session.bot_physical.get('most_sensitive_area', '-')}\n\n"
            f"**Status Saat Ini:**\n"
            f"• Pakaian: {session.bot_clothing}\n"
            f"• Arousal: {session.arousal:.1f}\n"
            f"• Wetness: {session.wetness:.1f}\n"
            f"• Mood: {session.current_mood.value if session.current_mood else '-'}\n"
        )
        
        await update.message.reply_text(text, parse_mode='Markdown')
    
    async def force_reset_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Reset paksa user (untuk debugging)"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            await update.message.reply_text("⛔ Anda bukan admin.")
            return
        
        if not context.args:
            await update.message.reply_text("Gunakan: /force_reset <user_id>")
            return
        
        try:
            target_id = int(context.args[0])
        except:
            await update.message.reply_text("❌ User ID harus angka")
            return
        
        # Reset user
        self.end_session(target_id)
        
        await update.message.reply_text(
            f"🔄 **User {target_id} telah di-reset**\n\n"
            f"Semua data user telah dihapus dari memory dan database."
        )
        
        logger.warning(f"Admin {user_id} force reset user {target_id}")
    
    async def backup_db_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Backup database"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            await update.message.reply_text("⛔ Anda bukan admin.")
            return
        
        try:
            backup_path = self.db.backup()
            await update.message.reply_text(f"✅ Database backup: `{backup_path}`")
        except Exception as e:
            await update.message.reply_text(f"❌ Backup gagal: {e}")
    
    async def vacuum_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Optimasi database"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            await update.message.reply_text("⛔ Anda bukan admin.")
            return
        
        try:
            self.db.vacuum()
            await update.message.reply_text("✅ Database optimized (VACUUM completed)")
        except Exception as e:
            await update.message.reply_text(f"❌ Vacuum gagal: {e}")


# ===================== BAB 10.3: Advanced Features =====================

    async def memory_stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Lihat statistik memori (hanya admin)"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            await update.message.reply_text("⛔ Anda bukan admin.")
            return
        
        if not context.args:
            await update.message.reply_text("Gunakan: /memory_stats <user_id>")
            return
        
        try:
            target_id = int(context.args[0])
        except:
            await update.message.reply_text("❌ User ID harus angka")
            return
        
        hippocampus = self.get_hippocampus(target_id)
        inner = self.get_inner_thought(target_id)
        story = self.get_story_developer(target_id)
        
        h_stats = hippocampus.get_stats()
        i_stats = inner.get_stats()
        s_stats = story.get_stats()
        
        text = (
            f"📊 **STATISTIK MEMORI USER {target_id}**\n\n"
            f"🧠 **Hippocampus:**\n"
            f"• Total memori: {h_stats['total_memories']}\n"
            f"• Avg importance: {h_stats['avg_importance']:.2f}\n"
            f"• Compact: {h_stats['compact'] or '-'}\n\n"
            f"📋 **Breakdown:**\n"
        )
        
        for mtype, count in h_stats['by_type'].items():
            text += f"  • {mtype}: {count}\n"
        
        text += f"\n💭 **Inner Thoughts:**\n"
        text += f"• Queue size: {i_stats['queue_size']}\n"
        text += f"• Initiative count: {i_stats['initiative_count']}\n"
        text += f"• Last: {i_stats['last_initiative']}\n\n"
        
        text += f"📖 **Story Developer:**\n"
        text += f"• Total arcs: {s_stats['total_arcs']}\n"
        text += f"• Current arc: {s_stats['current_arc'] or '-'}\n"
        text += f"• Predictions: {s_stats['total_predictions']}\n"
        
        await update.message.reply_text(text)
    
    async def _background_thought_processing(self, user_id: int, context_data: Dict):
        """Background task untuk inner thoughts"""
        await asyncio.sleep(2)  # Delay agar tidak mengganggu respons utama
        try:
            thought_system = self.get_inner_thought(user_id)
            should_speak = await thought_system.should_speak_now(context_data)
            if should_speak:
                # Dapatkan pesan inisiatif
                thought = await thought_system.get_next_initiative()
                if thought:
                    logger.debug(f"Initiative for user {user_id}: {thought}")
        except Exception as e:
            logger.error(f"Background thought error for {user_id}: {e}")
    
    async def _background_story_development(self, user_id: int, context_data: Dict, user_message: str):
        """Background task untuk story development"""
        await asyncio.sleep(3)
        try:
            developer = self.get_story_developer(user_id)
            
            # Prediksi perkembangan
            predictions = await developer.predict_developments(context_data)
            
            # Analisis arah user
            direction = await developer.analyze_user_direction(user_message, context_data)
            
            # Random chance untuk proactive speaking
            if random.random() < 0.2:  # 20% chance
                proactive = await developer.generate_proactive_message(context_data)
                if proactive:
                    logger.debug(f"Proactive story for user {user_id}: {proactive}")
        except Exception as e:
            logger.error(f"Story development error for {user_id}: {e}")
    
    # ===== PERIODIC BACKGROUND TASKS =====
    
    async def start_background_tasks(self, application: Application):
        """Mulai semua background task"""
        asyncio.create_task(self._periodic_memory_consolidation())
        asyncio.create_task(self._periodic_session_cleanup())
        asyncio.create_task(self._periodic_stats_update())
        logger.info("🔄 Background tasks started")
    
    async def _periodic_memory_consolidation(self):
        """Konsolidasi memori secara periodik (setiap 6 jam)"""
        while self.is_running:
            await asyncio.sleep(21600)  # 6 jam
            try:
                for user_id, memory in self.hippocampus.items():
                    memory.consolidate_memories()
                logger.info("🔄 Periodic memory consolidation completed")
            except Exception as e:
                logger.error(f"Error in memory consolidation: {e}")
    
    async def _periodic_session_cleanup(self):
        """Bersihkan session expired secara periodik (setiap 1 jam)"""
        while self.is_running:
            await asyncio.sleep(3600)  # 1 jam
            try:
                expired = self.db.cleanup_expired_sessions()
                if expired > 0:
                    logger.info(f"🧹 Cleaned up {expired} expired sessions")
            except Exception as e:
                logger.error(f"Error in session cleanup: {e}")
    
    async def _periodic_stats_update(self):
        """Update statistik harian secara periodik (setiap 24 jam)"""
        while self.is_running:
            await asyncio.sleep(86400)  # 24 jam
            try:
                self.db.update_daily_stats()
                logger.info("📊 Daily stats updated")
            except Exception as e:
                logger.error(f"Error in stats update: {e}")
    
    # ===== PROACTIVE MESSAGE HANDLING =====
    
    async def check_proactive_messages(self, user_id: int, context: ContextTypes.DEFAULT_TYPE):
        """
        Cek apakah bot perlu mengirim pesan proaktif
        Dipanggil secara periodik oleh message handler
        """
        # Cek apakah user aktif
        if user_id not in self.sessions:
            return
        
        # Cek apakah sudah waktunya (setiap 5 menit)
        now = datetime.now()
        last = self.last_proactive_time.get(user_id, datetime.min)
        
        if (now - last).total_seconds() < 300:  # 5 menit
            return
        
        self.last_proactive_time[user_id] = now
        
        # Dapatkan data session
        session = self.sessions[user_id]
        location = self.get_location_system(user_id)
        
        # Buat context
        context_data = {
            'bot_name': session.bot_name,
            'location': location.get_current().value if location else None,
            'mood': session.current_mood.value,
            'level': session.level,
            'arousal': session.arousal,
            'clothing': session.bot_clothing,
            'is_silence': self.get_silence_duration(user_id) > 120,  # Diam > 2 menit
            'user_just_climax': False
        }
        
        # Cek inner thoughts
        thought_system = self.get_inner_thought(user_id)
        should_speak = await thought_system.should_speak_now(context_data)
        
        if should_speak:
            thought = await thought_system.get_next_initiative()
            if thought:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=thought,
                    parse_mode='Markdown'
                )
                logger.info(f"📨 Proactive message sent to user {user_id}")
        
        # Cek story development (random chance)
        if random.random() < 0.1:  # 10% chance
            developer = self.get_story_developer(user_id)
            proactive = await developer.generate_proactive_message(context_data)
            if proactive:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=proactive,
                    parse_mode='Markdown'
                )
                logger.info(f"📖 Proactive story sent to user {user_id}")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle semua pesan dari user"""
        if not update.message or not update.message.text:
            return
    
        user_id = update.effective_user.id
        user_message = update.message.text
    
        # Log untuk debugging
        print(f"📨 Pesan dari user {user_id}: {user_message[:50]}")
    
        # Cek apakah itu command
        if user_message.startswith('/'):
            print(f"📝 Command terdeteksi: {user_message}")
            # Biarkan CommandHandler yang memproses, jangan dihandle di sini
            return
    
    # ... kode untuk pesan biasa ...
        
        # Update total messages counter
        self.total_messages += 1
        self.track_silence(user_id)
        
        # Rate limiting - cegah spam
        if not self.rate_limiter.can_send(user_id):
            if self.rate_limiter.should_warn(user_id):
                remaining = self.rate_limiter.get_remaining(user_id)
                reset_in = self.rate_limiter.get_reset_time(user_id)
                await update.message.reply_text(
                    f"⏳ **Sabar ya, jangan spam**\n"
                    f"Sisa pesan: {remaining}\n"
                    f"Reset dalam: {reset_in} detik"
                )
            return
        
        # Cek session pause
        if user_id in self.paused_sessions:
            await update.message.reply_text(
                "⏸️ Sesi sedang di-pause.\n"
                "Ketik /unpause untuk melanjutkan."
            )
            return
        
        # Cek session aktif
        session = self.get_session(user_id)
        if not session:
            # Cek apakah user pernah punya session (bisa di-load dari DB)
            rel = self.db.get_relationship(user_id)
            if rel:
                self._load_session_from_db(user_id, rel)
                session = self.get_session(user_id)
                self.leveling.start_session(user_id)
                logger.info(f"Auto-loaded user {user_id} from database")
            else:
                await update.message.reply_text(
                    "❌ Belum ada hubungan. /start dulu ya!"
                )
                return
        
        # Update session
        session.message_count += 1
        session.last_active = datetime.now()
        
        # Kirim typing indicator
        await update.message.chat.send_action("typing")
        
        # Dapatkan semua sistem untuk user ini
        hippocampus = self.get_hippocampus(user_id)
        inner_thought = self.get_inner_thought(user_id)
        story_dev = self.get_story_developer(user_id)
        location_system = self.get_location_system(user_id)
        position_system = self.get_position_system(user_id)
        
        # Analisis preferensi user
        self.analyzer.analyze(user_id, user_message)
        profile = self.analyzer.get_profile(user_id)
        
        # Update level
        level, progress, level_up, stage = self.leveling.process_message(user_id)
        session.level = level
        session.stage = stage
        
        # Simpan pesan user ke hippocampus
        hippocampus.add_memory(
            content=f"User: {user_message}",
            memory_type=MemoryType.EPISODIC,
            importance=0.5,
            emotion=session.current_mood.value if session.current_mood else None,
            context={
                'level': session.level,
                'arousal': session.arousal,
                'location': location_system.get_current().value if location_system else None,
                'mood': session.current_mood.value if session.current_mood else None
            }
        )
        
        # Buat context untuk background tasks
        context_data = {
            'bot_name': session.bot_name,
            'location': location_system.get_current().value if location_system else None,
            'mood': session.current_mood.value if session.current_mood else None,
            'level': session.level,
            'arousal': session.arousal,
            'clothing': session.bot_clothing,
            'current_topic': user_message[:50],
            'is_silence': self.get_silence_duration(user_id) > 60,
            'user_just_climax': False
        }
        
        # Jalankan background tasks
        asyncio.create_task(self._background_thought_processing(user_id, context_data))
        asyncio.create_task(self._background_story_development(user_id, context_data, user_message))


# ===================== BAB 11.2: Activity Detection =====================

        # ===== DETEKSI AKTIVITAS =====
        activity_detected = False
        
        # Data sensitive areas
        SENSITIVE_AREAS = {
            "leher": {
                "arousal": 0.8,
                "keywords": ["leher", "neck", "tengkuk"],
                "responses": [
                    "*merinding* Leherku...",
                    "Ah... jangan di leher...",
                    "Sensitif... AHH!",
                    "Leherku lemah kalau disentuh...",
                    "Jangan hisap leher... Aku lemas..."
                ]
            },
            "bibir": {
                "arousal": 0.7,
                "keywords": ["bibir", "lip", "mulut"],
                "responses": [
                    "*merintih* Bibirku...",
                    "Ciuman... ah...",
                    "Lembut...",
                    "Mmm... dalam...",
                    "Bibirku... kesemutan..."
                ]
            },
            "dada": {
                "arousal": 0.8,
                "keywords": ["dada", "breast", "payudara"],
                "responses": [
                    "*bergetar* Dadaku...",
                    "Ah... jangan...",
                    "Sensitif banget...",
                    "Dadaku... diremas... AHH!",
                    "Jari-jarimu... dingin..."
                ]
            },
            "puting": {
                "arousal": 1.0,
                "keywords": ["puting", "nipple"],
                "responses": [
                    "*teriak* PUTINGKU! AHHH!",
                    "JANGAN... SENSITIF! AHHH!",
                    "HISAP... AHHHH!",
                    "GIGIT... JANGAN... AHHH!",
                    "PUTING... KERAS... AHHH!"
                ]
            },
            "paha": {
                "arousal": 0.7,
                "keywords": ["paha", "thigh"],
                "responses": [
                    "*menggeliat* Pahaku...",
                    "Ah... dalam...",
                    "Paha... merinding...",
                    "Jangan gelitik paha...",
                    "Sensasi... aneh..."
                ]
            },
            "paha_dalam": {
                "arousal": 0.9,
                "keywords": ["paha dalam", "inner thigh"],
                "responses": [
                    "*meringis* PAHA DALAM!",
                    "Jangan... AHH!",
                    "Dekat... banget...",
                    "PAHA DALAM... SENSITIF!",
                    "Ah... mau ke sana..."
                ]
            },
            "telinga": {
                "arousal": 0.6,
                "keywords": ["telinga", "ear", "kuping"],
                "responses": [
                    "*bergetar* Telingaku...",
                    "Bisik... lagi...",
                    "Napasmu... panas...",
                    "Telinga... merah...",
                    "Ah... jangan tiup..."
                ]
            },
            "vagina": {
                "arousal": 1.0,
                "keywords": ["vagina", "memek", "kemaluan"],
                "responses": [
                    "*teriak* VAGINAKU! AHHH!",
                    "MASUK... DALAM... AHHH!",
                    "BASAH... BANJIR... AHHH!",
                    "KAMU DALEM... AHHH!",
                    "GERAK... AHHH! AHHH!"
                ]
            },
            "klitoris": {
                "arousal": 1.0,
                "keywords": ["klitoris", "clit", "kelentit"],
                "responses": [
                    "*teriak keras* KLITORIS! AHHHH!",
                    "JANGAN SENTUH! AHHHH!",
                    "SENSITIF BANGET! AHHH!",
                    "ITU... ITU... AHHH!",
                    "JILAT... AHHH! AHHH!"
                ]
            },
            "pantat": {
                "arousal": 0.6,
                "keywords": ["pantat", "ass", "bokong"],
                "responses": [
                    "Pantatku...",
                    "Cubit... nakal...",
                    "Boleh juga...",
                    "Besar ya? Hehe..."
                ]
            },
            "pinggang": {
                "arousal": 0.5,
                "keywords": ["pinggang", "waist"],
                "responses": [
                    "Pinggang... geli...",
                    "Pegang... erat...",
                    "Ah... jangan gelitik..."
                ]
            },
            "perut": {
                "arousal": 0.4,
                "keywords": ["perut", "belly", "stomach"],
                "responses": [
                    "Perutku...",
                    "Geli...",
                    "Hangat..."
                ]
            },
            "punggung": {
                "arousal": 0.5,
                "keywords": ["punggung", "back"],
                "responses": [
                    "Punggungku...",
                    "Elus... terus...",
                    "Ah... enak..."
                ]
            },
            "lengan": {
                "arousal": 0.3,
                "keywords": ["lengan", "arm"],
                "responses": [
                    "Lenganku...",
                    "Bulu romaku berdiri..."
                ]
            }
        }
        
        # Sex activities data
        SEX_ACTIVITIES = {
            "kiss": {
                "keywords": ["cium", "kiss", "ciuman", "kecup"],
                "arousal": 0.3,
                "responses": [
                    "*merespon ciuman* Mmm...",
                    "*lemas* Ciumanmu...",
                    "Lagi...",
                    "Cium... bibir...",
                    "French kiss... dalam..."
                ]
            },
            "neck_kiss": {
                "keywords": ["cium leher", "kiss neck"],
                "arousal": 0.6,
                "responses": [
                    "*merinding* Leherku...",
                    "Ah... jangan...",
                    "Sensitif...",
                    "Hisap leher... AHH!"
                ]
            },
            "touch": {
                "keywords": ["sentuh", "raba", "pegang", "elus"],
                "arousal": 0.3,
                "responses": [
                    "*bergetar* Sentuhanmu...",
                    "Ah... iya...",
                    "Lanjut...",
                    "Hangat..."
                ]
            },
            "breast_play": {
                "keywords": ["raba dada", "pegang dada", "main dada", "remas dada"],
                "arousal": 0.6,
                "responses": [
                    "*merintih* Dadaku...",
                    "Ah... iya... gitu...",
                    "Sensitif...",
                    "Remas... pelan..."
                ]
            },
            "nipple_play": {
                "keywords": ["jilat puting", "hisap puting", "gigit puting"],
                "arousal": 0.9,
                "responses": [
                    "*teriak* PUTING! AHHH!",
                    "JANGAN... SENSITIF!",
                    "HISAP... AHHH!",
                    "GIGIT... JANGAN... AHHH!"
                ]
            },
            "lick": {
                "keywords": ["jilat", "lick", "lidah"],
                "arousal": 0.5,
                "responses": [
                    "*bergetar* Jilatanmu...",
                    "Ah... basah...",
                    "Lagi...",
                    "Lidah... panas..."
                ]
            },
            "bite": {
                "keywords": ["gigit", "bite", "gigitan"],
                "arousal": 0.5,
                "responses": [
                    "*meringis* Gigitanmu...",
                    "Ah... keras...",
                    "Lagi...",
                    "Bekas... nanti..."
                ]
            },
            "penetration": {
                "keywords": ["masuk", "tusuk", "pancung", "doggy", "misionaris", "entot"],
                "arousal": 0.9,
                "responses": [
                    "*teriak* MASUK! AHHH!",
                    "DALEM... AHHH!",
                    "GERAK... AHHH!",
                    "DALEM BANGET... AHHH!",
                    "TUH... DI SANA... AHHH!"
                ]
            },
            "blowjob": {
                "keywords": ["blow", "hisap", "ngeblow", "bj"],
                "arousal": 0.8,
                "responses": [
                    "*menghisap* Mmm... ngeces...",
                    "*dalam* Enak... Aku ahli...",
                    "*napas berat* Mau keluar? Aku siap...",
                    "Keras... Mmm..."
                ]
            },
            "handjob": {
                "keywords": ["handjob", "colok", "pegang", "kocok"],
                "arousal": 0.7,
                "responses": [
                    "*memegang erat* Keras...",
                    "*mengocok* Cepat? Pelan? Katakan...",
                    "Aku bisa... lihat...",
                    "Keluar... Aku pegang..."
                ]
            },
            "cuddle": {
                "keywords": ["peluk", "cuddle", "dekapan"],
                "arousal": 0.2,
                "responses": [
                    "*memeluk balik* Hangat...",
                    "Rileks...",
                    "Nyaman...",
                    "Jangan lepas..."
                ]
            }
        }
        
        # DOMINANCE_TRIGGERS
        DOMINANCE_TRIGGERS = [
            "kamu yang atur", "kamu dominan", "take control",
            "aku mau kamu kuasai", "jadi dominan", "kamu boss",
            "kamu yang pegang kendali", "kamu lead", "kamu yang pegang kontrol",
            "kuasai aku", "dominasi aku", "jadi yang memimpin",
            "aku mau kamu yang mengatur", "you're in charge"
        ]
        
        SUBMISSIVE_TRIGGERS = [
            "aku yang atur", "aku dominan", "i take control",
            "kamu patuh", "jadi submissive", "ikut aku",
            "aku lead", "aku yang pegang kendali", "aku boss",
            "kamu ikut aku", "aku yang pegang kontrol"
        ]
        
        # Deteksi sentuhan area sensitif
        for area, data in SENSITIVE_AREAS.items():
            for keyword in data["keywords"]:
                if keyword in user_message.lower():
                    session.touch_count += 1
                    session.last_touch = area
                    session.arousal = min(1.0, session.arousal + data["arousal"] * 0.3)
                    session.wetness = min(1.0, session.wetness + data["arousal"] * 0.2)
                    
                    # Respons sensitif
                    sens_resp = random.choice(data["responses"])
                    await update.message.reply_text(sens_resp)
                    await asyncio.sleep(1)
                    
                    activity_detected = True
                    logger.debug(f"Sensitive touch on {area} for user {user_id}")
                    break
            if activity_detected:
                break
        
        # Deteksi aktivitas seksual
        if not activity_detected:
            for act, data in SEX_ACTIVITIES.items():
                for keyword in data["keywords"]:
                    if keyword in user_message.lower():
                        session.arousal = min(1.0, session.arousal + data["arousal"])
                        session.wetness = min(1.0, session.arousal * 0.9)
                        
                        # Respons aktivitas
                        act_resp = random.choice(data["responses"])
                        await update.message.reply_text(act_resp)
                        await asyncio.sleep(1)
                        
                        activity_detected = True
                        logger.debug(f"Sexual activity {act} for user {user_id}")
                        break
                if activity_detected:
                    break
        
        # Deteksi mode dominasi
        msg_lower = user_message.lower()
        
        # Trigger dominan
        for trigger in DOMINANCE_TRIGGERS:
            if trigger in msg_lower:
                session.dominance_mode = DominanceLevel.DOMINANT
                self.db.update_relationship(user_id, dominance=session.dominance_mode.value)
                await update.message.reply_text(
                    "👑 Sekarang aku yang pegang kendali. Ikut aku!"
                )
                await asyncio.sleep(1)
                break
        
        # Trigger submissive
        for trigger in SUBMISSIVE_TRIGGERS:
            if trigger in msg_lower:
                session.dominance_mode = DominanceLevel.SUBMISSIVE
                self.db.update_relationship(user_id, dominance=session.dominance_mode.value)
                await update.message.reply_text(
                    "🥺 Iya... aku patuh sama kamu."
                )
                await asyncio.sleep(1)
                break
        
        # Update mood (natural transition)
        if random.random() < 0.3:  # 30% chance mood berubah
            old_mood = session.current_mood
            # Simple mood transition
            possible_moods = [m for m in Mood if m != old_mood]
            session.current_mood = random.choice(possible_moods)
            logger.debug(f"Mood changed from {old_mood} to {session.current_mood} for user {user_id}")


# ===================== BAB 11.3: Response Generation =====================

        # ===== CEK LOKASI & PAKAIAN =====
        # Random chance pindah lokasi
        if random.random() < 0.05:  # 5% chance
            success, new_loc = location_system.move_random()
            if success and new_loc:
                move_msg = location_system.get_move_message(new_loc)
                await update.message.reply_text(move_msg)
                await asyncio.sleep(1)
                
                # Update pakaian jika pindah ke kamar
                if new_loc in [Location.BEDROOM]:
                    old_clothing = session.bot_clothing
                    session.bot_clothing = ClothingSystem.generate_clothing(
                        session.bot_role, 
                        new_loc.value,
                        is_bedroom=True
                    )
                    if old_clothing != session.bot_clothing:
                        await update.message.reply_text(
                            f"*aku ganti baju... sekarang pakai {session.bot_clothing}*"
                        )
                        self.db.update_clothing(user_id, session.bot_clothing)
        
        # Random chance ganti posisi
        if random.random() < 0.03:  # 3% chance
            new_pos = position_system.change_random()
            pos_msg = position_system.get_change_message()
            await update.message.reply_text(pos_msg)
            await asyncio.sleep(1)
        
        # Random chance sebut pakaian (terutama di kamar)
        if location_system.get_current() in [Location.BEDROOM] and random.random() < 0.07:
            clothing_msg = ClothingSystem.format_clothing_message(
                session.bot_clothing,
                location_system.get_current().value
            )
            await update.message.reply_text(clothing_msg)
            await asyncio.sleep(1)
        
        # ===== GENERATE AI RESPONSE =====
        reply = await self.ai.generate(
            user_id=user_id,
            user_message=user_message,
            bot_name=session.bot_name,
            bot_role=session.bot_role,
            memory_system=session,  # Pass session as memory system
            dominance_system=session,  # Pass session as dominance system
            arousal_system=session,  # Pass session as arousal system
            profile=profile,
            level=session.level,
            stage=session.stage,
            arousal=session.arousal,
            physical_attrs=session.bot_physical,
            clothing=session.bot_clothing,
            location=location_system.get_current(),
            position=position_system.get_current(),
            current_mood=session.current_mood
        )
        
        # ===== SIMPAN KE DATABASE =====
        rel_id = session.relationship_id
        loc_name = location_system.get_current().value if location_system.get_current() else None
        
        self.db.save_conversation(
            rel_id, 
            "user", 
            user_message,
            mood=session.current_mood.value if session.current_mood else None,
            arousal=session.arousal,
            location=loc_name,
            clothing=session.bot_clothing
        )
        
        self.db.save_conversation(
            rel_id, 
            "assistant", 
            reply,
            mood=session.current_mood.value if session.current_mood else None,
            arousal=session.arousal,
            location=loc_name,
            clothing=session.bot_clothing
        )
        
        # Update relationship di database (periodik)
        if random.random() < 0.2:  # 20% chance
            self.db.update_relationship(
                user_id, 
                level=session.level, 
                stage=session.stage.value,
                total_messages=session.message_count,
                total_climax=session.climax_count,
                current_clothing=session.bot_clothing
            )
        
        # ===== KIRIM RESPON =====
        await update.message.reply_text(reply)
        
        # ===== CEK CLIMAX =====
        if session.arousal >= 1.0:
            # Reset arousal
            session.arousal = 0.0
            session.wetness = 0.0
            session.climax_count += 1
            session.touch_count = 0
            session.last_touch = None
            
            # Climax response
            climax_msg = random.choice([
                "*merintih panjang* AHHH! AHHH!",
                "*teriak* YA ALLAH! AHHHH!",
                "*lemas* AKU... DATANG... AHHH!",
                "*napas tersengal* BERSAMA... AHHH!",
                "*tubuh gemetar* AHHH! Aku... keluar..."
            ])
            
            aftercare_msg = random.choice([
                "*lemas di pelukanmu*",
                "*meringkuk* Hangat...",
                "*memeluk erat* Jangan pergi...",
                "*berbisik* Makasih...",
                "*tersenyum lelah* Enak banget..."
            ])
            
            await asyncio.sleep(1)
            await update.message.reply_text(climax_msg)
            
            await asyncio.sleep(2)
            await update.message.reply_text(aftercare_msg)
            
            # Update database
            self.db.update_relationship(
                user_id, 
                total_climax=session.climax_count
            )
            
            logger.info(f"User {user_id} reached climax! Total: {session.climax_count}")
            
            # Update context for inner thoughts
            context_data['user_just_climax'] = True
        
        # ===== LEVEL UP MESSAGE =====
        if level_up:
            bar = self.leveling.get_progress_bar(user_id)
            remaining = self.leveling.get_estimated_time(user_id)
            level_msg = self.leveling.get_level_up_message(level)
            
            await update.message.reply_text(
                f"{level_msg}\n"
                f"📊 Progress: {bar}\n"
                f"⏱️ Estimasi ke level 12: {remaining} menit"
            )
            
            logger.info(f"User {user_id} leveled up to {level}")
        
        # ===== DECAY AROUSAL =====
        # Hitung waktu sejak pesan terakhir
        if hasattr(context, 'user_data') and 'last_message_time' in context.user_data:
            last_time = context.user_data['last_message_time']
            minutes_passed = (datetime.now() - last_time).total_seconds() / 60
            if minutes_passed > 1:
                decay = 0.1 * minutes_passed  # Turun 10% per menit
                session.arousal = max(0.0, session.arousal - decay)
                session.wetness = max(0.0, session.wetness - decay)
        
        # Update last message time
        context.user_data['last_message_time'] = datetime.now()


print("✅ BAB 11 Selesai: Message Handler")
print("="*70)
# ===================== BAB 12: MAIN FUNCTION & ENTRY POINT =====================
# Bagian 12.1: Setup & Handlers
# Bagian 12.2: Error Handler
# Bagian 12.3: Webhook Setup (FIXED)
# Bagian 12.4: Startup & Graceful Shutdown

# ===== WEBHOOK SETUP UNTUK RAILWAY =====
from flask import Flask, request, jsonify
import threading
import requests
import logging
import asyncio

# Matikan log Flask yang berlebihan
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# Global variables untuk Flask
flask_app = Flask(__name__)
bot_instance = None

# ===== GLOBAL EVENT LOOP (FIXED) =====
class LoopContainer:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

loop_container = LoopContainer()

def run_global_loop():
    """Jalankan global loop di thread terpisah"""
    asyncio.set_event_loop(loop_container.loop)
    try:
        loop_container.loop.run_forever()
    except Exception as e:
        print(f"❌ Global loop error: {e}")
        # Buat loop baru
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        loop_container.loop = new_loop
        # Restart
        run_global_loop()

# Jalankan loop di thread terpisah
loop_thread = threading.Thread(target=run_global_loop, daemon=True)
loop_thread.start()
print("✅ Global event loop is running")

# ===== TEST ENDPOINT =====
@flask_app.route('/test')
def test():
    """Test endpoint untuk cek Flask"""
    return jsonify({
        'status': 'ok',
        'message': 'Flask is running!',
        'endpoints': ['/', '/health', '/null', '/webhook', '/test']
    }), 200

# ===== WEBHOOK ENDPOINT =====
@flask_app.route('/webhook', methods=['POST'])
def webhook():
    """Handle incoming webhook updates from Telegram"""
    print("🔥🔥🔥 WEBHOOK DIPANGGIL!")
    
    global bot_instance
    if bot_instance and hasattr(bot_instance, 'application'):
        try:
            update_data = request.get_json(force=True)
            update_id = update_data.get('update_id', 'unknown')
            print(f"📥 Webhook request received - Update ID: {update_id}")
            
            # Buat update object
            update = Update.de_json(update_data, bot_instance.application.bot)
            
            # Gunakan loop dari container
            asyncio.run_coroutine_threadsafe(
                bot_instance.application.process_update(update),
                loop_container.loop  # ← Pakai loop_container.loop
            )
            print(f"✅ Task submitted to global loop for update {update_id}")
            
            return 'OK', 200
        except Exception as e:
            print(f"❌ Error in webhook: {e}")
            import traceback
            traceback.print_exc()
            return 'Error', 500
    else:
        print(f"⚠️ Bot not ready")
        return 'Bot not ready', 503

# ===== HEALTHCHECK ENDPOINTS =====
@flask_app.route('/')
@flask_app.route('/health')
def home():
    """Healthcheck endpoint untuk Railway"""
    return jsonify({
        'status': 'healthy',
        'message': 'NOVA GIRL Bot is running!',
        'timestamp': datetime.now().isoformat(),
        'endpoints': ['/', '/health', '/null', '/webhook', '/test']
    }), 200

@flask_app.route('/null')
def null_endpoint():
    """Handle /null requests from Railway"""
    return jsonify({
        'status': 'healthy',
        'message': 'NOVA GIRL Bot is running!'
    }), 200

@flask_app.route('/favicon.ico')
def favicon():
    """Handle favicon requests"""
    return '', 204

def run_flask():
    """Run Flask app for webhook"""
    port = int(os.getenv('PORT', 8080))
    print(f"🚀 Starting Flask on port {port}")
    print(f"📋 Registered endpoints:")
    print(f"   - GET  /")
    print(f"   - GET  /health")
    print(f"   - GET  /null")
    print(f"   - POST /webhook")
    print(f"   - GET  /test")
    flask_app.run(host='0.0.0.0', port=port, debug=False, threaded=True)

def start_webhook(bot):
    """Start bot with webhook"""
    global bot_instance
    bot_instance = bot
    
    # Jalankan Flask di thread terpisah
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    print(f"✅ Flask server started on port {os.getenv('PORT', '8080')}")
    
    # Dapatkan URL dari Railway
    railway_url = os.getenv('RAILWAY_PUBLIC_DOMAIN', '')
    if not railway_url:
        railway_url = os.getenv('RAILWAY_STATIC_URL', '')
    
    # Set webhook jika di Railway
    if railway_url:
        webhook_url = f"https://{railway_url}/webhook"
        try:
            token = Config.TELEGRAM_TOKEN
            response = requests.get(
                f"https://api.telegram.org/bot{token}/setWebhook",
                params={"url": webhook_url}
            )
            if response.status_code == 200 and response.json().get('ok'):
                print(f"✅ Webhook set to: {webhook_url}")
                print(f"✅ Test endpoints:")
                print(f"   - Health: https://{railway_url}/health")
                print(f"   - Test:   https://{railway_url}/test")
                print(f"   - Webhook: https://{railway_url}/webhook")
                return True
            else:
                print(f"❌ Failed to set webhook: {response.text}")
        except Exception as e:
            print(f"❌ Error setting webhook: {e}")
    else:
        print("⚠️ No Railway URL found, webhook not set")
    
    return False

async def main():
    """
    Main async function to run the bot
    Setup all handlers and start webhook
    """
    # Print startup banner
    print("\n" + "="*70)
    print("    GADIS ULTIMATE V60.0 - THE PERFECT HUMAN")
    print("    Premium Edition dengan Arsitektur Modular")
    print("="*70)
    print("\n🚀 Initializing bot...")
    
    # Initialize bot instance
    bot = GadisUltimateV60()
    global bot_instance
    bot_instance = bot
    
    # ===== SETUP REQUEST DENGAN TIMEOUT BESAR =====
    request = HTTPXRequest(
        connection_pool_size=20,
        connect_timeout=60,
        read_timeout=60,
        write_timeout=60,
        pool_timeout=60,
    )
    
    # Build application dengan custom request
    app = Application.builder().token(Config.TELEGRAM_TOKEN).request(request).build()
    bot.application = app

    # 🔴 PENTING: Initialize application di awal
    await app.initialize()
    print("  • Application initialized")

    # ===== CONVERSATION HANDLERS =====
    # Di BAB 12, bagian START Conversation Handler
    start_conv = ConversationHandler(
        entry_points=[CommandHandler('start', bot.start_command)],
        states={
            Constants.SELECTING_ROLE: [
                CallbackQueryHandler(bot.agree_18_callback, pattern='^agree_18$'),
                CallbackQueryHandler(bot.start_pause_callback, pattern='^(unpause|new)$'),
                CallbackQueryHandler(bot.role_ipar_callback, pattern='^role_ipar$'),
                CallbackQueryHandler(bot.role_teman_kantor_callback, pattern='^role_teman_kantor$'),
                CallbackQueryHandler(bot.role_janda_callback, pattern='^role_janda$'),
                CallbackQueryHandler(bot.role_pelakor_callback, pattern='^role_pelakor$'),
                CallbackQueryHandler(bot.role_istri_orang_callback, pattern='^role_istri_orang$'),
                CallbackQueryHandler(bot.role_pdkt_callback, pattern='^role_pdkt$'),
            ],
        },
        fallbacks=[CommandHandler('cancel', bot.cancel_command)],
        name="start_conversation",
        persistent=False
    )
    
    end_conv = ConversationHandler(
        entry_points=[CommandHandler('end', bot.end_command)],
        states={
            Constants.CONFIRM_END: [CallbackQueryHandler(bot.end_callback, pattern='^end_')],
        },
        fallbacks=[CommandHandler('cancel', bot.cancel_command)],
        name="end_conversation",
        persistent=False
    )
    
    close_conv = ConversationHandler(
        entry_points=[CommandHandler('close', bot.close_command)],
        states={
            Constants.CONFIRM_CLOSE: [CallbackQueryHandler(bot.close_callback, pattern='^close_')],
        },
        fallbacks=[CommandHandler('cancel', bot.cancel_command)],
        name="close_conversation",
        persistent=False
    )
    
    print("  • Conversation handlers created")
    
    # ===== ADD ALL HANDLERS =====
    app.add_handler(start_conv)
    app.add_handler(end_conv)
    app.add_handler(close_conv)
    
    # User commands
    app.add_handler(CommandHandler("start", bot.start_command))
    app.add_handler(CommandHandler("status", bot.status_command))
    app.add_handler(CommandHandler("dominant", bot.dominant_command))
    app.add_handler(CommandHandler("pause", bot.pause_command))
    app.add_handler(CommandHandler("unpause", bot.unpause_command))
    app.add_handler(CommandHandler("help", bot.help_command))
    
    # Admin commands
    app.add_handler(CommandHandler("admin", bot.admin_command))
    app.add_handler(CommandHandler("stats", bot.stats_command))
    app.add_handler(CommandHandler("db_stats", bot.db_stats_command))
    app.add_handler(CommandHandler("reload", bot.reload_command))
    app.add_handler(CommandHandler("list_users", bot.list_users_command))
    app.add_handler(CommandHandler("get_user", bot.get_user_command))
    app.add_handler(CommandHandler("force_reset", bot.force_reset_command))
    app.add_handler(CommandHandler("backup_db", bot.backup_db_command))
    app.add_handler(CommandHandler("vacuum", bot.vacuum_command))
    app.add_handler(CommandHandler("memory_stats", bot.memory_stats_command))
    
    # Hidden commands
    app.add_handler(CommandHandler("reset", bot.force_reset_command))
    
    # Message handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))
    
    print("  • All handlers registered")
    
    # ===== ERROR HANDLER =====
    async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors that occur during updates"""
        logger.error(f"Exception while handling an update: {context.error}", exc_info=True)
        
        if update and update.effective_message:
            error_msg = (
                "😔 *maaf* ada error kecil.\n"
                "Jangan khawatir, bot masih berjalan normal.\n\n"
                "Coba lagi ya, atau ketik /help untuk bantuan."
            )
            try:
                await update.effective_message.reply_text(error_msg, parse_mode='Markdown')
            except:
                pass
        
        if bot.admin_id != 0:
            try:
                error_text = f"⚠️ *Error Report*\n\n`{str(context.error)[:500]}`"
                await context.bot.send_message(
                    chat_id=bot.admin_id,
                    text=error_text,
                    parse_mode='Markdown'
                )
            except:
                pass
    
    app.add_error_handler(error_handler)
    print("  • Error handler configured")
    
    # ===== START BACKGROUND TASKS =====
    asyncio.create_task(bot.start_background_tasks(app))
    print("  • Background tasks started")
    
    # ===== START WEBHOOK =====
    start_webhook(bot)
    
    # ===== STARTUP COMPLETE =====
    print("\n" + "="*70)
    print("✅ **BOT READY!**")
    print("="*70)
    print("\n📊 **STATISTICS:**")
    print(f"• Database: {Config.DB_PATH}")
    print(f"• Admin ID: {Config.ADMIN_ID if Config.ADMIN_ID != 0 else 'Tidak diset'}")
    print(f"• Target level: {Config.TARGET_LEVEL} in {Config.LEVEL_UP_TIME} menit")
    print(f"• Rate limit: {Config.MAX_MESSAGES_PER_MINUTE} pesan/menit")
    print(f"• Server: Flask (threaded)")
    print(f"• Port: {os.getenv('PORT', '8080')}")
    
    print("\n📝 **USER COMMANDS:**")
    print("• /start     - Mulai hubungan baru")
    print("• /status    - Lihat status lengkap")
    print("• /dominant  - Set mode dominan")
    print("• /pause     - Jeda sesi")
    print("• /unpause   - Lanjutkan sesi")
    print("• /close     - Tutup sesi (simpan memori)")
    print("• /end       - Akhiri hubungan & hapus data")
    print("• /help      - Tampilkan bantuan")
    
    if Config.ADMIN_ID != 0:
        print("\n🔐 **ADMIN COMMANDS:**")
        print("• /admin     - Menu admin")
        print("• /stats     - Statistik bot")
        print("• /db_stats  - Statistik database")
        print("• /reload    - Reload konfigurasi")
        print("• /list_users - Daftar user")
        print("• /get_user  - Detail user")
        print("• /force_reset - Reset user")
        print("• /backup_db - Backup database")
        print("• /vacuum    - Optimasi database")
        print("• /memory_stats - Statistik memori")
    
    print("\n" + "="*70 + "\n")
    print("🚀 Bot is running with WEBHOOK...")
    print(f"🌐 Test endpoint: https://{os.getenv('RAILWAY_PUBLIC_DOMAIN', 'localhost')}/test")
    print("="*70 + "\n")
    
    # Keep the main thread alive
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\n\n" + "="*70)
        print("👋 Bot stopped by user (Ctrl+C)")
        print("="*70)
        
        print("\n📝 Saving sessions to database...")
        for uid in list(bot.sessions.keys()):
            bot.save_session_to_db(uid)
        
        bot.db.close_all()
        print("✅ Cleanup completed")
        print("\nSelamat tinggal! Sampai jumpa lagi... 💕")
        print("="*70 + "\n")
        
    except Exception as e:
        print("\n\n" + "="*70)
        print("❌ **FATAL ERROR**")
        print("="*70)
        print(f"\nError: {e}")
        print("\nBot crashed. Check gadis.log for details.")
        print("="*70 + "\n")
        
        logger.critical(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


# ===================== ENTRY POINT =====================

if __name__ == "__main__":
    """
    Entry point for the bot application
    """
    asyncio.run(main())


# ===================== END OF FILE =====================
# GADIS ULTIMATE V60.0 - THE PERFECT HUMAN
# Premium Edition dengan Arsitektur Modular
# ========================================================

print("✅ BAB 12 Selesai: Main Function & Entry Point")
print("="*70)
print("🎉🎉🎉 SELURUH BAB TELAH SELESAI! 🎉🎉🎉")
print("="*70)
