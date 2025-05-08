
// Analiz Sayfası için JavaScript Fonksiyonları
// ---------------------------------------

// AI Analiz API Çağrıları
async function getSalesAnalysis(salesData) {
  try {
    const response = await fetch('/ai/satis-analizi', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ satis_verileri: salesData }),
    });
    
    return await response.json();
  } catch (error) {
    console.error('Satış analizi hatası:', error);
    return { success: false, error: error.message };
  }
}

async function getTrendPrediction(historicalData, period = 'bir ay') {
  try {
    const response = await fetch('/ai/trend-tahmini', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ 
        gecmis_veriler: historicalData,
        tahmin_suresi: period 
      }),
    });
    
    return await response.json();
  } catch (error) {
    console.error('Trend tahmini hatası:', error);
    return { success: false, error: error.message };
  }
}

async function getDashboardAnalysis(dashboardData) {
  try {
    const response = await fetch('/ai/dashboard-analiz', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ dashboard_verileri: dashboardData }),
    });
    
    return await response.json();
  } catch (error) {
    console.error('Dashboard analizi hatası:', error);
    return { success: false, error: error.message };
  }
}

// Veri İşleme Yardımcı Fonksiyonlar

// Tarih formatını düzenle: YYYY-MM-DD -> DD.MM.YYYY
function formatDate(dateStr) {
  const parts = dateStr.split('-');
  if (parts.length !== 3) return dateStr;
  return `${parts[2]}.${parts[1]}.${parts[0]}`;
}

// Sayıları Türkçe formatında gösterme: 1234.56 -> 1.234,56
function formatCurrency(value) {
  return value.toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// Zaman serisi verilerinde hareketli ortalama hesaplama
function calculateMovingAverage(data, period = 7) {
  if (!Array.isArray(data) || data.length === 0) return [];
  
  const result = [];
  
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) {
      // İlk (period-1) eleman için yeterli veri yok
      result.push(null);
    } else {
      // Son 'period' sayıda elemanın ortalamasını al
      let sum = 0;
      for (let j = 0; j < period; j++) {
        sum += data[i - j];
      }
      result.push(sum / period);
    }
  }
  
  return result;
}

// Ürün satışlarını kategorilere göre grupla
function groupProductsByCategory(products) {
  if (!Array.isArray(products) || products.length === 0) return {};
  
  const categories = {};
  
  products.forEach(product => {
    // Örnek bir kategori belirleme algoritması
    // Gerçek uygulamada ürün ID'sine göre veya diğer bir kurala göre kategoriler belirlenebilir
    const categoryName = determineCategoryFromProductId(product.product_id);
    
    if (!categories[categoryName]) {
      categories[categoryName] = {
        totalSales: 0,
        totalRevenue: 0,
        products: []
      };
    }
    
    categories[categoryName].totalSales += product.sale_count || 0;
    categories[categoryName].totalRevenue += product.total_revenue || 0;
    categories[categoryName].products.push(product);
  });
  
  return categories;
}

// Ürün ID'sine göre kategori belirle (basit bir örnek)
function determineCategoryFromProductId(productId) {
  if (!productId) return 'Bilinmeyen';
  
  // Ürün ID'leri bazı kurallara göre kategorilere ayrılabilir
  // Bu örnekte ürün ID'sinin ilk karakterine göre yapıyoruz
  const firstChar = (productId.toString().charAt(0) || '').toLowerCase();
  
  if ('abc'.includes(firstChar)) {
    return 'Kadın Ayakkabı';
  } else if ('def'.includes(firstChar)) {
    return 'Erkek Ayakkabı';
  } else if ('ghi'.includes(firstChar)) {
    return 'Çocuk Ayakkabı';
  } else if ('jkl'.includes(firstChar)) {
    return 'Çanta';
  } else {
    return 'Diğer';
  }
}

// Satış tahminleri oluşturma (basit doğrusal regresyon)
function predictSales(historicalData, daysToPredict = 30) {
  if (!Array.isArray(historicalData) || historicalData.length === 0) {
    return Array(daysToPredict).fill(0);
  }
  
  // Basit bir doğrusal regresyon modeli
  // y = mx + b formülü için m (eğim) ve b (y-eksenini kesme) değerlerini hesapla
  
  // Verilerimizi x ve y değerlerine dönüştürelim
  const n = historicalData.length;
  let sumX = 0;
  let sumY = 0;
  let sumXY = 0;
  let sumXX = 0;
  
  for (let i = 0; i < n; i++) {
    sumX += i;
    sumY += historicalData[i];
    sumXY += i * historicalData[i];
    sumXX += i * i;
  }
  
  // Doğrusal regresyon formülü
  const m = (n * sumXY - sumX * sumY) / (n * sumXX - sumX * sumX);
  const b = (sumY - m * sumX) / n;
  
  // Gelecek değerleri tahmin et
  const predictions = [];
  for (let i = 0; i < daysToPredict; i++) {
    predictions.push(m * (n + i) + b);
  }
  
  return predictions;
}

// Dışa aktarma fonksiyonu (CSV formatı)
function exportToCSV(data, filename = 'analiz_raporu.csv') {
  if (!data || !Array.isArray(data) || data.length === 0) {
    console.error('Dışa aktarılacak veri bulunamadı');
    return;
  }
  
  // Sütun başlıklarını al
  const headers = Object.keys(data[0]);
  
  // CSV satırlarını oluştur
  let csvContent = headers.join(',') + '\n';
  
  data.forEach(row => {
    const values = headers.map(header => {
      const value = row[header];
      // Tırnak içine alınması gereken değerleri kontrol et
      const formattedValue = typeof value === 'string' && value.includes(',') ? 
        `"${value}"` : value;
      return formattedValue;
    });
    csvContent += values.join(',') + '\n';
  });
  
  // CSV dosyasını indir
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const link = document.createElement('a');
  const url = URL.createObjectURL(blob);
  
  link.setAttribute('href', url);
  link.setAttribute('download', filename);
  link.style.visibility = 'hidden';
  
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

// Dışa aktarma fonksiyonu (PDF formatı)
function exportToPDF(elementId, filename = 'analiz_raporu.pdf') {
  alert('PDF dışa aktarma özelliği yapım aşamasındadır. Önce bir PDF kütüphanesi entegre edilmelidir (örn: jsPDF veya html2pdf).');
}
