// Gelişmiş Gerçekçi Hava Durumu Animasyonu
(function () {
  const canvas = document.getElementById("weatherCanvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");

  // Hava durumu bilgisi
  const weatherDesc = (document.querySelector('meta[name="weather-description"]')?.content || '').toLowerCase();
  const weatherCode = parseInt(document.querySelector('meta[name="weather-code"]')?.content || '0');
  const cloudPercent = parseInt(document.querySelector('meta[name="weather-clouds"]')?.content || '0');
  
  // Rüzgar bilgisi (meta tag'den al, yoksa varsayılan)
  const windSpeed = parseFloat(document.querySelector('meta[name="weather-wind"]')?.content || '10');
  const windDirection = parseFloat(document.querySelector('meta[name="weather-wind-direction"]')?.content || '180');

  // Hava durumu tespiti
  const isOvercast = weatherCode === 3 || cloudPercent >= 75 || weatherDesc.includes('kapalı') || weatherDesc.includes('bulutlu');
  const isRainy = weatherCode >= 51 || weatherDesc.includes('yağmur') || weatherDesc.includes('sağanak');
  const isSnowy = (weatherCode >= 71 && weatherCode <= 86) || weatherDesc.includes('kar');
  const showSun = !isOvercast && !isRainy && !isSnowy;

  // Rüzgar hızına göre hareket çarpanı (0-50 km/h arası normalize)
  const windMultiplier = Math.min(windSpeed / 20, 2.5);
  // Rüzgar yönü (derece -> radyan, 0=kuzey, 90=doğu, 180=güney, 270=batı)
  const windAngle = (windDirection - 90) * (Math.PI / 180);
  const windX = Math.cos(windAngle) * windMultiplier;
  const windY = Math.sin(windAngle) * windMultiplier * 0.3;

  // Saat bilgisi (İstanbul)
  function getHour() {
    try {
      return new Date(new Date().toLocaleString("en-US", { timeZone: "Europe/Istanbul" })).getHours();
    } catch (e) {
      return new Date().getHours();
    }
  }
  const hour = getHour();
  const isDay = hour >= 7 && hour < 18;

  // Ay fazı hesaplama (0=yeni ay, 0.5=dolunay, 1=yeni ay)
  function getMoonPhase() {
    const now = new Date();
    const year = now.getFullYear();
    const month = now.getMonth() + 1;
    const day = now.getDate();
    
    // Basit ay fazı hesaplama (Synodic ay = 29.53 gün)
    const c = Math.floor(365.25 * year) + Math.floor(30.6 * month) + day - 694039.09;
    const phase = c / 29.53;
    return phase - Math.floor(phase);
  }
  const moonPhase = getMoonPhase();

  let clouds = [];
  let raindrops = [];
  let snowflakes = [];
  let stars = [];
  let shootingStars = [];

  function resize() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    initClouds();
    initStars();
    if (isRainy) initRain();
    if (isSnowy) initSnow();
  }

  // Bulutlar - 10-15 adet, farklı şekiller
  function initClouds() {
    clouds = [];
    const count = isOvercast ? 15 : 10;
    for (let i = 0; i < count; i++) {
      clouds.push({
        x: Math.random() * (canvas.width + 400) - 200,
        y: 15 + Math.random() * canvas.height * 0.4,
        scale: 0.6 + Math.random() * 1.0,
        baseSpeed: 0.1 + Math.random() * 0.15,
        opacity: isOvercast ? (0.88 + Math.random() * 0.12) : (0.6 + Math.random() * 0.25),
        type: Math.floor(Math.random() * 4), // 4 farklı bulut tipi
        puffs: [] // Her bulutun kendi puf dizisi
      });
      // Her bulut için rastgele puflar oluştur
      const puffCount = 5 + Math.floor(Math.random() * 5);
      for (let j = 0; j < puffCount; j++) {
        clouds[i].puffs.push({
          offsetX: (Math.random() - 0.5) * 120,
          offsetY: (Math.random() - 0.5) * 40,
          size: 20 + Math.random() * 35
        });
      }
    }
  }

  // Yıldızlar - 60+ farklı yıldız
  function initStars() {
    stars = [];
    for (let i = 0; i < 70; i++) {
      stars.push({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height * 0.7,
        size: 0.5 + Math.random() * 2,
        brightness: 0.3 + Math.random() * 0.7,
        twinkleSpeed: 0.5 + Math.random() * 2,
        twinkleOffset: Math.random() * Math.PI * 2,
        color: Math.random() > 0.7 ? 
          (Math.random() > 0.5 ? '#ffe4c4' : '#add8e6') : '#ffffff' // Bazıları sarımsı/mavimsi
      });
    }
    // Kayan yıldızlar
    shootingStars = [];
  }

  // Kayan yıldız oluştur
  function createShootingStar() {
    if (shootingStars.length < 2 && Math.random() < 0.005) {
      shootingStars.push({
        x: Math.random() * canvas.width * 0.8,
        y: Math.random() * canvas.height * 0.3,
        length: 50 + Math.random() * 100,
        speed: 8 + Math.random() * 12,
        angle: Math.PI / 4 + (Math.random() - 0.5) * 0.5,
        life: 1,
        decay: 0.015 + Math.random() * 0.01
      });
    }
  }

  // Yağmur - detaylı
  function initRain() {
    raindrops = [];
    const intensity = weatherDesc.includes('şiddetli') || weatherDesc.includes('sağanak') ? 180 : 120;
    for (let i = 0; i < intensity; i++) {
      raindrops.push({
        x: Math.random() * canvas.width * 1.5,
        y: Math.random() * canvas.height,
        speed: 12 + Math.random() * 10,
        length: 15 + Math.random() * 20,
        thickness: 1 + Math.random() * 1.5,
        opacity: 0.3 + Math.random() * 0.4
      });
    }
  }

  // Kar taneleri - detaylı ve farklı şekiller
  function initSnow() {
    snowflakes = [];
    for (let i = 0; i < 100; i++) {
      snowflakes.push({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height,
        size: 2 + Math.random() * 6,
        speed: 0.5 + Math.random() * 2,
        swing: Math.random() * Math.PI * 2,
        swingSpeed: 0.01 + Math.random() * 0.02,
        rotation: Math.random() * Math.PI * 2,
        rotationSpeed: (Math.random() - 0.5) * 0.05,
        type: Math.floor(Math.random() * 3), // 3 farklı kar tanesi tipi
        opacity: 0.6 + Math.random() * 0.4
      });
    }
  }

  // Gökyüzü
  function drawSky() {
    const gradient = ctx.createLinearGradient(0, 0, 0, canvas.height);
    
    if (!isDay) {
      gradient.addColorStop(0, "#0a0a1a");
      gradient.addColorStop(0.3, "#0f1638");
      gradient.addColorStop(0.7, "#1a237e");
      gradient.addColorStop(1, "#283593");
    } else if (isOvercast) {
      gradient.addColorStop(0, "#90a4ae");
      gradient.addColorStop(0.4, "#b0bec5");
      gradient.addColorStop(1, "#cfd8dc");
    } else if (hour < 9) {
      gradient.addColorStop(0, "#6eb5ff");
      gradient.addColorStop(0.4, "#87CEEB");
      gradient.addColorStop(0.7, "#ffd4a3");
      gradient.addColorStop(1, "#ffb347");
    } else if (hour >= 16) {
      gradient.addColorStop(0, "#4a6fa5");
      gradient.addColorStop(0.3, "#ff8c42");
      gradient.addColorStop(0.6, "#ff6b35");
      gradient.addColorStop(1, "#d63031");
    } else {
      gradient.addColorStop(0, "#2980b9");
      gradient.addColorStop(0.4, "#56CCF2");
      gradient.addColorStop(0.8, "#87CEEB");
      gradient.addColorStop(1, "#a8d8ea");
    }
    
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
  }

  // Yıldızlar ve kayan yıldızlar
  function drawStars() {
    if (isDay || isOvercast) return;
    
    const time = Date.now() * 0.001;
    
    // Sabit yıldızlar
    stars.forEach(star => {
      const twinkle = Math.sin(time * star.twinkleSpeed + star.twinkleOffset);
      const alpha = star.brightness * (0.5 + twinkle * 0.5);
      
      ctx.fillStyle = star.color;
      ctx.globalAlpha = alpha;
      ctx.beginPath();
      ctx.arc(star.x, star.y, star.size, 0, Math.PI * 2);
      ctx.fill();
      
      // Büyük yıldızlara ışın efekti
      if (star.size > 1.5 && alpha > 0.6) {
        ctx.strokeStyle = star.color;
        ctx.lineWidth = 0.5;
        ctx.globalAlpha = alpha * 0.3;
        const rayLen = star.size * 3;
        ctx.beginPath();
        ctx.moveTo(star.x - rayLen, star.y);
        ctx.lineTo(star.x + rayLen, star.y);
        ctx.moveTo(star.x, star.y - rayLen);
        ctx.lineTo(star.x, star.y + rayLen);
        ctx.stroke();
      }
    });
    ctx.globalAlpha = 1;
    
    // Kayan yıldızlar
    createShootingStar();
    shootingStars.forEach((star, index) => {
      ctx.save();
      ctx.translate(star.x, star.y);
      ctx.rotate(star.angle);
      
      const gradient = ctx.createLinearGradient(0, 0, -star.length * star.life, 0);
      gradient.addColorStop(0, `rgba(255, 255, 255, ${star.life})`);
      gradient.addColorStop(0.3, `rgba(255, 255, 200, ${star.life * 0.7})`);
      gradient.addColorStop(1, 'rgba(255, 255, 255, 0)');
      
      ctx.strokeStyle = gradient;
      ctx.lineWidth = 2;
      ctx.lineCap = 'round';
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.lineTo(-star.length * star.life, 0);
      ctx.stroke();
      
      // Parlak baş
      ctx.fillStyle = `rgba(255, 255, 255, ${star.life})`;
      ctx.beginPath();
      ctx.arc(0, 0, 2, 0, Math.PI * 2);
      ctx.fill();
      
      ctx.restore();
      
      star.x += Math.cos(star.angle) * star.speed;
      star.y += Math.sin(star.angle) * star.speed;
      star.life -= star.decay;
      
      if (star.life <= 0) {
        shootingStars.splice(index, 1);
      }
    });
  }

  // Güneş
  function drawSun() {
    if (!isDay || !showSun) return;
    
    const x = canvas.width * 0.88;
    const y = canvas.height * 0.12;
    
    // Işık halesi
    const glow = ctx.createRadialGradient(x, y, 25, x, y, 150);
    glow.addColorStop(0, "rgba(255, 250, 200, 0.5)");
    glow.addColorStop(0.4, "rgba(255, 220, 120, 0.2)");
    glow.addColorStop(1, "rgba(255, 200, 100, 0)");
    ctx.fillStyle = glow;
    ctx.beginPath();
    ctx.arc(x, y, 150, 0, Math.PI * 2);
    ctx.fill();
    
    // Ana güneş
    ctx.beginPath();
    const sunGrad = ctx.createRadialGradient(x, y, 0, x, y, 40);
    sunGrad.addColorStop(0, "#FFFEF0");
    sunGrad.addColorStop(0.3, "#FFF59D");
    sunGrad.addColorStop(0.7, "#FFEB3B");
    sunGrad.addColorStop(1, "#FFC107");
    ctx.fillStyle = sunGrad;
    ctx.arc(x, y, 40, 0, Math.PI * 2);
    ctx.fill();
  }

  // Gerçekçi Ay (faz hesaplı)
  function drawMoon() {
    if (isDay || isOvercast) return;
    
    const x = canvas.width * 0.85;
    const y = canvas.height * 0.18;
    const radius = 28;
    
    // Ay ışığı halesi
    const glow = ctx.createRadialGradient(x, y, radius, x, y, radius * 3);
    glow.addColorStop(0, "rgba(255, 255, 240, 0.2)");
    glow.addColorStop(0.5, "rgba(200, 200, 220, 0.1)");
    glow.addColorStop(1, "rgba(255, 255, 255, 0)");
    ctx.fillStyle = glow;
    ctx.beginPath();
    ctx.arc(x, y, radius * 3, 0, Math.PI * 2);
    ctx.fill();
    
    // Ay yüzeyi
    ctx.save();
    ctx.beginPath();
    ctx.arc(x, y, radius, 0, Math.PI * 2);
    ctx.clip();
    
    // Ay ana rengi
    const moonGrad = ctx.createRadialGradient(x - 5, y - 5, 0, x, y, radius);
    moonGrad.addColorStop(0, "#FFFFF5");
    moonGrad.addColorStop(0.5, "#F5F5DC");
    moonGrad.addColorStop(1, "#E8E4C9");
    ctx.fillStyle = moonGrad;
    ctx.fillRect(x - radius, y - radius, radius * 2, radius * 2);
    
    // Kraterler
    ctx.fillStyle = "rgba(180, 175, 160, 0.25)";
    ctx.beginPath();
    ctx.arc(x - 8, y - 10, 7, 0, Math.PI * 2);
    ctx.fill();
    ctx.beginPath();
    ctx.arc(x + 12, y + 5, 5, 0, Math.PI * 2);
    ctx.fill();
    ctx.beginPath();
    ctx.arc(x - 5, y + 12, 6, 0, Math.PI * 2);
    ctx.fill();
    ctx.beginPath();
    ctx.arc(x + 8, y - 8, 4, 0, Math.PI * 2);
    ctx.fill();
    ctx.beginPath();
    ctx.arc(x + 2, y + 2, 3, 0, Math.PI * 2);
    ctx.fill();
    
    // Ay fazı gölgesi
    ctx.restore();
    ctx.save();
    ctx.beginPath();
    ctx.arc(x, y, radius, 0, Math.PI * 2);
    ctx.clip();
    
    // Faz hesaplama (0-0.5 = büyüyen, 0.5-1 = küçülen)
    const phaseAngle = moonPhase * Math.PI * 2;
    const shadowOffset = Math.cos(phaseAngle) * radius * 2;
    
    ctx.fillStyle = "rgba(10, 10, 26, 0.95)";
    ctx.beginPath();
    if (moonPhase < 0.5) {
      // Büyüyen ay - sağdan sola gölge
      ctx.ellipse(x + shadowOffset, y, Math.abs(shadowOffset), radius, 0, 0, Math.PI * 2);
    } else {
      // Küçülen ay - soldan sağa gölge
      ctx.ellipse(x + shadowOffset, y, Math.abs(shadowOffset), radius, 0, 0, Math.PI * 2);
    }
    ctx.fill();
    
    ctx.restore();
  }

  // Gelişmiş bulut çizimi - farklı şekiller
  function drawCloud(cloud) {
    ctx.save();
    ctx.translate(cloud.x, cloud.y);
    ctx.scale(cloud.scale, cloud.scale);
    
    const baseColor = isOvercast ? 200 : 255;
    const shadowColor = isOvercast ? 160 : 220;
    
    // Alt gölge
    ctx.fillStyle = `rgba(${shadowColor}, ${shadowColor + 5}, ${shadowColor + 10}, ${cloud.opacity * 0.4})`;
    ctx.beginPath();
    ctx.ellipse(0, 18, 80, 20, 0, 0, Math.PI * 2);
    ctx.fill();
    
    // Her bulutun kendi pufları
    ctx.fillStyle = `rgba(${baseColor}, ${baseColor}, ${baseColor}, ${cloud.opacity})`;
    cloud.puffs.forEach(puff => {
      ctx.beginPath();
      ctx.arc(puff.offsetX, puff.offsetY, puff.size, 0, Math.PI * 2);
      ctx.fill();
    });
    
    // Tip bazlı ekstra detaylar
    if (cloud.type === 0) {
      // Kabarık bulut
      ctx.beginPath();
      ctx.arc(0, -15, 35, 0, Math.PI * 2);
      ctx.fill();
    } else if (cloud.type === 1) {
      // Uzun bulut
      ctx.beginPath();
      ctx.ellipse(0, 0, 70, 25, 0, 0, Math.PI * 2);
      ctx.fill();
    } else if (cloud.type === 2) {
      // Çift tepeli
      ctx.beginPath();
      ctx.arc(-25, -20, 28, 0, Math.PI * 2);
      ctx.arc(25, -18, 30, 0, Math.PI * 2);
      ctx.fill();
    } else {
      // Katmanlı
      ctx.beginPath();
      ctx.arc(0, 0, 40, 0, Math.PI * 2);
      ctx.arc(-40, 5, 30, 0, Math.PI * 2);
      ctx.arc(40, 5, 32, 0, Math.PI * 2);
      ctx.fill();
    }
    
    ctx.restore();
  }

  function drawClouds() {
    clouds.forEach(cloud => {
      drawCloud(cloud);
      // Rüzgara göre hız
      cloud.x += cloud.baseSpeed + windX;
      cloud.y += windY * 0.5;
      
      // Sınır kontrolü
      if (cloud.x > canvas.width + 250) {
        cloud.x = -250;
        cloud.y = 15 + Math.random() * canvas.height * 0.4;
      }
      if (cloud.x < -300) {
        cloud.x = canvas.width + 200;
      }
      // Y ekseninde sınırla
      cloud.y = Math.max(15, Math.min(canvas.height * 0.45, cloud.y));
    });
  }

  // Detaylı yağmur
  function drawRain() {
    if (!isRainy) return;
    
    raindrops.forEach(drop => {
      // Rüzgara göre eğik yağmur
      const dropAngle = Math.atan2(drop.speed, windX * 3);
      const endX = drop.x + Math.sin(dropAngle) * drop.length;
      const endY = drop.y + Math.cos(dropAngle) * drop.length;
      
      // Yağmur damlası gradient
      const gradient = ctx.createLinearGradient(drop.x, drop.y, endX, endY);
      gradient.addColorStop(0, `rgba(180, 200, 230, ${drop.opacity * 0.3})`);
      gradient.addColorStop(0.5, `rgba(200, 220, 250, ${drop.opacity})`);
      gradient.addColorStop(1, `rgba(220, 235, 255, ${drop.opacity * 0.5})`);
      
      ctx.strokeStyle = gradient;
      ctx.lineWidth = drop.thickness;
      ctx.lineCap = 'round';
      ctx.beginPath();
      ctx.moveTo(drop.x, drop.y);
      ctx.lineTo(endX, endY);
      ctx.stroke();
      
      // Hareket - rüzgar etkisi
      drop.y += drop.speed;
      drop.x += windX * 2;
      
      // Yere düşünce sıçrama efekti (basit)
      if (drop.y > canvas.height) {
        drop.y = -drop.length - Math.random() * 50;
        drop.x = Math.random() * canvas.width * 1.5 - canvas.width * 0.25;
      }
    });
  }

  // Detaylı kar taneleri
  function drawSnow() {
    if (!isSnowy) return;
    
    snowflakes.forEach(flake => {
      ctx.save();
      ctx.translate(flake.x, flake.y);
      ctx.rotate(flake.rotation);
      ctx.globalAlpha = flake.opacity;
      
      if (flake.type === 0) {
        // Basit kar tanesi - altı kollu
        drawSnowflakeStar(flake.size);
      } else if (flake.type === 1) {
        // Kristal kar tanesi
        drawSnowflakeCrystal(flake.size);
      } else {
        // Yuvarlak kar
        ctx.fillStyle = 'white';
        ctx.beginPath();
        ctx.arc(0, 0, flake.size * 0.5, 0, Math.PI * 2);
        ctx.fill();
      }
      
      ctx.restore();
      
      // Hareket - rüzgar ve sallanma etkisi
      flake.y += flake.speed;
      flake.swing += flake.swingSpeed;
      flake.x += Math.sin(flake.swing) * 0.8 + windX * 0.5;
      flake.rotation += flake.rotationSpeed;
      
      if (flake.y > canvas.height + flake.size) {
        flake.y = -flake.size * 2;
        flake.x = Math.random() * canvas.width;
      }
    });
  }

  // Altı kollu kar tanesi
  function drawSnowflakeStar(size) {
    ctx.strokeStyle = 'white';
    ctx.lineWidth = 1;
    ctx.lineCap = 'round';
    
    for (let i = 0; i < 6; i++) {
      ctx.save();
      ctx.rotate(i * Math.PI / 3);
      
      // Ana kol
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.lineTo(0, -size);
      ctx.stroke();
      
      // Yan dallar
      ctx.beginPath();
      ctx.moveTo(0, -size * 0.4);
      ctx.lineTo(-size * 0.25, -size * 0.6);
      ctx.moveTo(0, -size * 0.4);
      ctx.lineTo(size * 0.25, -size * 0.6);
      ctx.stroke();
      
      ctx.beginPath();
      ctx.moveTo(0, -size * 0.7);
      ctx.lineTo(-size * 0.15, -size * 0.85);
      ctx.moveTo(0, -size * 0.7);
      ctx.lineTo(size * 0.15, -size * 0.85);
      ctx.stroke();
      
      ctx.restore();
    }
  }

  // Kristal kar tanesi
  function drawSnowflakeCrystal(size) {
    ctx.strokeStyle = 'white';
    ctx.lineWidth = 1.5;
    ctx.lineCap = 'round';
    
    for (let i = 0; i < 6; i++) {
      ctx.save();
      ctx.rotate(i * Math.PI / 3);
      
      // Ana kol
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.lineTo(0, -size);
      ctx.stroke();
      
      // Uç kristaller
      ctx.beginPath();
      ctx.moveTo(-size * 0.2, -size);
      ctx.lineTo(0, -size * 1.15);
      ctx.lineTo(size * 0.2, -size);
      ctx.stroke();
      
      ctx.restore();
    }
    
    // Merkez
    ctx.fillStyle = 'rgba(255, 255, 255, 0.8)';
    ctx.beginPath();
    ctx.arc(0, 0, size * 0.15, 0, Math.PI * 2);
    ctx.fill();
  }

  function animate() {
    drawSky();
    drawStars();
    drawSun();
    drawMoon();
    drawClouds();
    drawRain();
    drawSnow();
    requestAnimationFrame(animate);
  }

  window.addEventListener("resize", resize);
  resize();
  animate();

  console.log('[WEATHER] Durum:', weatherDesc, '| Kod:', weatherCode, '| Rüzgar:', windSpeed, 'km/h @', windDirection + '°', '| Ay fazı:', (moonPhase * 100).toFixed(0) + '%');
})();
