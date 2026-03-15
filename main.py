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

