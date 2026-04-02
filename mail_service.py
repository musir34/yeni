import os
import json
import smtplib
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Bildirim olay tanımları
NOTIFY_EVENTS = {
    'archive_added':     'Arşive Eklendiğinde',
    'status_kontrol':    'Kontrol Ediliyor statüsüne geçtiğinde',
    'status_uretiliyor': 'Üretiliyor statüsüne geçtiğinde',
    'status_hazir':      'Hazır statüsüne geçtiğinde',
    'status_iptal':      'İptal edildiğinde',
    'archive_restored':  'Arşivden çıkarıldığında',
}

# Statü -> olay eşlemesi
STATUS_EVENT_MAP = {
    'Kontrol Ediliyor': 'status_kontrol',
    'Üretiliyor':       'status_uretiliyor',
    'Hazır':            'status_hazir',
    'İptal Edildi':     'status_iptal',
}

# Kaynak görünen adları
SOURCE_LABELS = {
    'trendyol':    ('Trendyol', '#FF6F00'),
    'shopify':     ('Shopify', '#96BF48'),
    'woocommerce': ('WooCommerce', '#7B51AD'),
}

# Statü renkleri
STATUS_COLORS = {
    'Beklemede':         '#FFC107',
    'İşleme Alındı':    '#28A745',
    'Kontrol Ediliyor':  '#17A2B8',
    'Üretiliyor':        '#0D6EFD',
    'Hazır':             '#28A745',
    'Kargoya Verildi':   '#FD7E14',
    'İptal Edildi':      '#DC3545',
}

# Olay başlık renkleri
EVENT_COLORS = {
    'archive_added':     '#0D6EFD',
    'status_kontrol':    '#17A2B8',
    'status_uretiliyor': '#FFC107',
    'status_hazir':      '#28A745',
    'status_iptal':      '#DC3545',
    'archive_restored':  '#6F42C1',
}

# Olay başlıkları
EVENT_TITLES = {
    'archive_added':     'Sipariş Arşive Eklendi',
    'status_kontrol':    'Statü Değişti → Kontrol Ediliyor',
    'status_uretiliyor': 'Statü Değişti → Üretiliyor',
    'status_hazir':      'Statü Değişti → Hazır',
    'status_iptal':      'Sipariş İptal Edildi',
    'archive_restored':  'Sipariş Arşivden Çıkarıldı',
}


def _parse_products(details) -> list[dict]:
    """Sipariş details alanını ürün listesine çevirir."""
    if not details:
        return []
    if isinstance(details, str):
        try:
            details = json.loads(details)
        except (json.JSONDecodeError, TypeError):
            return []
    if isinstance(details, dict):
        details = [details]
    if not isinstance(details, list):
        return []
    return details


def _build_product_rows(products: list[dict], base_url: str) -> str:
    """Ürünler için HTML tablo satırları oluşturur."""
    if not products:
        return '<tr><td colspan="3" style="padding:12px;text-align:center;color:#999;">Ürün bilgisi yok</td></tr>'

    rows = ''
    for p in products:
        sku = p.get('sku') or p.get('merchantSku') or '-'
        barcode = p.get('barcode') or '-'
        image_url = p.get('imageUrl') or p.get('image_url') or ''

        if image_url and not image_url.startswith('http'):
            image_url = f"{base_url}{image_url}"

        img_html = f'<img src="{image_url}" width="60" height="60" style="border-radius:6px;object-fit:cover;border:1px solid #eee;" />' if image_url else '<div style="width:60px;height:60px;background:#f0f0f0;border-radius:6px;display:flex;align-items:center;justify-content:center;color:#ccc;font-size:12px;">Yok</div>'

        rows += f'''<tr>
            <td style="padding:8px;border-bottom:1px solid #f0f0f0;">{img_html}</td>
            <td style="padding:8px;border-bottom:1px solid #f0f0f0;font-weight:600;">{sku}</td>
            <td style="padding:8px;border-bottom:1px solid #f0f0f0;color:#666;">{barcode}</td>
        </tr>'''
    return rows


def build_email_html(event: str, order_number: str, customer_name: str,
                     source: str, products: list[dict],
                     reason: str | None = None, new_status: str | None = None,
                     base_url: str = '') -> str:
    """Detaylı ve güzel HTML email oluşturur."""

    title = EVENT_TITLES.get(event, 'Bildirim')
    title_color = EVENT_COLORS.get(event, '#333')
    source_label, source_color = SOURCE_LABELS.get(source, ('Bilinmiyor', '#999'))
    status_color = STATUS_COLORS.get(new_status, '#6C757D') if new_status else None

    # Ekstra bilgi satırları
    extra_rows = ''
    if reason:
        extra_rows += f'''<tr>
            <td style="padding:8px 0;color:#666;width:140px;">Arşivlenme Nedeni</td>
            <td style="padding:8px 0;font-weight:600;">{reason}</td>
        </tr>'''
    if new_status:
        extra_rows += f'''<tr>
            <td style="padding:8px 0;color:#666;width:140px;">Yeni Durum</td>
            <td style="padding:8px 0;"><span style="background:{status_color};color:#fff;padding:4px 12px;border-radius:20px;font-size:13px;font-weight:600;">{new_status}</span></td>
        </tr>'''

    product_rows = _build_product_rows(products, base_url)

    return f'''<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f4f6f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<div style="max-width:520px;margin:20px auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">

    <!-- Başlık -->
    <div style="background:{title_color};padding:20px 24px;">
        <h2 style="margin:0;color:#fff;font-size:18px;">{title}</h2>
    </div>

    <!-- İçerik -->
    <div style="padding:24px;">
        <table style="width:100%;border-collapse:collapse;">
            <tr>
                <td style="padding:8px 0;color:#666;width:140px;">Sipariş No</td>
                <td style="padding:8px 0;font-weight:700;font-size:15px;">{order_number}</td>
            </tr>
            <tr>
                <td style="padding:8px 0;color:#666;">Sipariş Kaynağı</td>
                <td style="padding:8px 0;"><span style="background:{source_color};color:#fff;padding:4px 12px;border-radius:20px;font-size:13px;font-weight:600;">{source_label}</span></td>
            </tr>
            <tr>
                <td style="padding:8px 0;color:#666;">Müşteri</td>
                <td style="padding:8px 0;font-weight:600;">{customer_name}</td>
            </tr>
            {extra_rows}
        </table>

        <!-- Ürünler -->
        <div style="margin-top:20px;padding-top:16px;border-top:2px solid #f0f0f0;">
            <h3 style="margin:0 0 12px;font-size:15px;color:#333;">Ürünler</h3>
            <table style="width:100%;border-collapse:collapse;">
                <tr style="background:#f8f9fa;">
                    <th style="padding:8px;text-align:left;font-size:12px;color:#999;font-weight:600;">GÖRSEL</th>
                    <th style="padding:8px;text-align:left;font-size:12px;color:#999;font-weight:600;">STOK KODU</th>
                    <th style="padding:8px;text-align:left;font-size:12px;color:#999;font-weight:600;">BARKOD</th>
                </tr>
                {product_rows}
            </table>
        </div>
    </div>

    <!-- Footer -->
    <div style="padding:16px 24px;background:#f8f9fa;text-align:center;border-top:1px solid #eee;">
        <p style="margin:0;font-size:12px;color:#aaa;">Güllü Ayakkabı — Sipariş Bildirim Sistemi</p>
    </div>

</div>
</body>
</html>'''


def _get_recipients_for_event(event: str) -> list[str]:
    """Belirli bir olay için bildirim açık olan kullanıcıların emaillerini döner."""
    try:
        from models import User
        users = User.query.filter_by(status='active').all()
        recipients = []
        for u in users:
            if u.notify_events and event in u.notify_events.split(','):
                if u.email:
                    recipients.append(u.email)
        return recipients
    except Exception as e:
        print(f"Bildirim alıcıları alınamadı: {e}")
        return []


def send_email(subject: str, body: str, to_emails: list[str] | None = None) -> bool:
    """Gmail SMTP üzerinden mail gönderir."""
    gmail_user = os.environ.get("GMAIL_USER")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD")

    if not all([gmail_user, gmail_password]):
        print("Mail ayarları eksik: GMAIL_USER, GMAIL_APP_PASSWORD kontrol edin.")
        return False

    if not to_emails:
        print("Mail gönderilecek alıcı yok.")
        return False

    msg = MIMEMultipart()
    msg["From"] = gmail_user
    msg["To"] = ", ".join(to_emails)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "html"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(gmail_user, gmail_password)
            server.send_message(msg)
        print(f"Mail gönderildi: {subject} -> {to_emails}")
        return True
    except Exception as e:
        print(f"Mail gönderme hatası: {e}")
        return False


def notify(event: str, subject: str, body: str) -> None:
    """
    Belirli bir olay için bildirim gönderir (arka planda).
    Sadece o olayı seçmiş kullanıcılara mail gider.
    """
    from app import app

    def _send():
        with app.app_context():
            recipients = _get_recipients_for_event(event)
            if recipients:
                send_email(subject, body, recipients)

    thread = threading.Thread(target=_send)
    thread.daemon = True
    thread.start()
