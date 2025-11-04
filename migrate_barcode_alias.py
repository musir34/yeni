"""
Barkod Alias Tablosu Oluşturma Migration
═══════════════════════════════════════════

Bu script barcode_aliases tablosunu oluşturur.

Kullanım:
    python migrate_barcode_alias.py
    
veya Flask shell'den:
    from migrate_barcode_alias import create_barcode_alias_table
    create_barcode_alias_table()
"""

from models import db
from app import app


def create_barcode_alias_table():
    """BarcodeAlias tablosunu oluşturur"""
    
    with app.app_context():
        # Tabloyu oluştur
        with db.engine.connect() as conn:
            conn.execute(db.text("""
                CREATE TABLE IF NOT EXISTS barcode_aliases (
                    alias_barcode VARCHAR(100) PRIMARY KEY,
                    main_barcode VARCHAR(100) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by VARCHAR(100),
                    note VARCHAR(255)
                );
            """))
            
            # Index oluştur (hızlı arama için)
            conn.execute(db.text("""
                CREATE INDEX IF NOT EXISTS idx_barcode_aliases_main 
                ON barcode_aliases(main_barcode);
            """))
            
            conn.commit()
        
        print("✅ barcode_aliases tablosu başarıyla oluşturuldu!")
        print("✅ Index'ler oluşturuldu!")


if __name__ == "__main__":
    print("🔧 Barkod Alias Migration başlatılıyor...")
    print()
    
    try:
        create_barcode_alias_table()
        print()
        print("🎉 Migration tamamlandı!")
        print()
        print("Kullanım:")
        print("  1. /barcode-alias/ adresine git")
        print("  2. Alias ekle formunu kullan")
        print("  3. Alias'lar otomatik olarak tüm sistemde çalışacak")
        
    except Exception as e:
        print(f"❌ Hata: {e}")
        print()
        print("Sorun giderme:")
        print("  - Veritabanı bağlantısını kontrol et")
        print("  - app.py dosyasının doğru yapılandırıldığından emin ol")
