
from models import db
from order_status_manager import migrate_orders_to_status_tables
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app():
    app = Flask(__name__)
    # Veritabanı bağlantı bilgilerini, ana uygulamanızın gerçek bağlantı bilgileriyle değiştirmelisiniz
    app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:postgres@localhost:5432/siparisyonetim'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    return app
