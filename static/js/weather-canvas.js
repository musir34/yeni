// Gelişmiş Hava Durumu Canvas Animasyon Sistemi
// Gerçekçi güneş, yağmur, kar, şimşek efektleri

(function () {
  const canvas = document.getElementById("weatherCanvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  
  // Hava durumu bilgisi (backend'den gelen) - EN BAŞTA TANIMLA
  const weatherElement = document.querySelector('meta[name="weather-description"]');
  const weatherCode = weatherElement ? weatherElement.content.toLowerCase() : 'açık hava';
  
  // Partiküller
  let raindrops = [];
  let snowflakes = [];
  let lightningFlash = 0;
  let lightningTimer = 0;
  
  // Yıldızlar
  let stars = [];
  function initStars() {
    stars = [];
    for(let i=0; i<200; i++) {
      stars.push({
        x: Math.random()*canvas.width,
        y: Math.random()*canvas.height,
        r: 1 + Math.random()*2,
        a: 0.3 + Math.random()*0.7,
        twinkleSpeed: 0.01 + Math.random()*0.02
      });
    }
  }
  
  // Bulutlar
  let clouds = [];
  function makeClouds() {
    clouds = [];
    const count = 10;
    for(let i=0; i<count; i++) {
      clouds.push({
        x: Math.random()*(canvas.width+300)-150,
        y: Math.random()*canvas.height*0.5,
        w: 140+Math.random()*200,
        h: 70+Math.random()*50,
        s: 0.1+Math.random()*0.3,
        opacity: 0.3+Math.random()*0.5,
        puffs: Math.floor(4 + Math.random()*4)
      });
    }
  }
  
  // Yağmur
  function initRain() {
    raindrops = [];
    const intensity = weatherCode.includes('şiddetli') ? 200 : weatherCode.includes('sağanak') ? 150 : 100;
    for(let i=0; i<intensity; i++) {
      raindrops.push({
        x: Math.random()*canvas.width,
        y: Math.random()*canvas.height,
        l: 15+Math.random()*25,
        xs: -3+Math.random()*6,
        ys: 12+Math.random()*12,
        opacity: 0.3+Math.random()*0.5
      });
    }
  }
  
  // Kar
  function initSnow() {
    snowflakes = [];
    for(let i=0; i<120; i++) {
      snowflakes.push({
        x: Math.random()*canvas.width,
        y: Math.random()*canvas.height,
        r: 2+Math.random()*5,
        xs: -1.5+Math.random()*3,
        ys: 1+Math.random()*4,
        opacity: 0.5+Math.random()*0.5,
        rotation: Math.random()*Math.PI*2
      });
    }
  }
  
  function initParticles() {
    if(weatherCode.includes('yağmur') || weatherCode.includes('sağanak') || weatherCode.includes('çisel')) {
      initRain();
    } else if(weatherCode.includes('kar')) {
      initSnow();
    }
  }
  
  // Canvas boyutlandırma ve başlatma
  function resize(){
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    initStars();
    makeClouds();
    initParticles();
  }
  window.addEventListener("resize", resize);
  resize();
  
  function istHour(){
    try{
      return new Date(new Date().toLocaleString("en-US",{timeZone:"Europe/Istanbul"})).getHours();
    }catch(e){
      return new Date().getHours();
    }
  }
  
  function drawBG(){
    const h = istHour();
    const isDay = h >= 6 && h < 20;
    
    // Gradient gökyüzü
    const gradient = ctx.createLinearGradient(0, 0, 0, canvas.height);
    if(isDay) {
      if(h >= 6 && h < 8) {
        gradient.addColorStop(0, "#FF7E5F");
        gradient.addColorStop(0.4, "#FFB347");
        gradient.addColorStop(1, "#FED99B");
      } else if(h >= 8 && h < 17) {
        gradient.addColorStop(0, "#4A90E2");
        gradient.addColorStop(0.5, "#87CEEB");
        gradient.addColorStop(1, "#B0E0E6");
      } else {
        gradient.addColorStop(0, "#FF6B6B");
        gradient.addColorStop(0.5, "#FFA07A");
        gradient.addColorStop(1, "#FFD1A4");
      }
    } else {
      gradient.addColorStop(0, "#0B0B1F");
      gradient.addColorStop(0.5, "#1A1A3E");
      gradient.addColorStop(1, "#2C2C54");
    }
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    
    if(isDay) {
      drawSun(h);
      drawClouds();
    } else {
      drawMoon();
      drawStars();
    }
    
    drawWeatherEffects();
  }
  
  function drawSun(h){
    const p = Math.max(0, Math.min(1, (h-6)/12));
    const x = canvas.width*0.15 + p*canvas.width*0.7;
    const y = canvas.height*0.85 - Math.sin(p*Math.PI)*canvas.height*0.7;
    const time = Date.now() * 0.0001;
    
    // Işık hüzmeleri (dönen)
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(time);
    for(let i=0; i<20; i++) {
      ctx.rotate(Math.PI/10);
      const rayGrad = ctx.createLinearGradient(0, 0, 0, -140);
      rayGrad.addColorStop(0, "rgba(255,220,100,0.7)");
      rayGrad.addColorStop(0.5, "rgba(255,180,50,0.4)");
      rayGrad.addColorStop(1, "rgba(255,200,50,0)");
      ctx.fillStyle = rayGrad;
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.lineTo(-10, -140);
      ctx.lineTo(10, -140);
      ctx.closePath();
      ctx.fill();
    }
    ctx.restore();
    
    // Hale efektleri (çoklu katman)
    for(let i=4; i>0; i--) {
      ctx.beginPath();
      const haloSize = 90 + i*35;
      const haloGrad = ctx.createRadialGradient(x,y,60,x,y,haloSize);
      haloGrad.addColorStop(0, `rgba(255,215,100,${0.12*i})`);
      haloGrad.addColorStop(1, "rgba(255,215,100,0)");
      ctx.fillStyle = haloGrad;
      ctx.arc(x,y,haloSize,0,2*Math.PI);
      ctx.fill();
    }
    
    // Ana güneş cismi
    ctx.beginPath();
    const sunGrad = ctx.createRadialGradient(x,y,0,x,y,85);
    sunGrad.addColorStop(0, "#FFFEF0");
    sunGrad.addColorStop(0.3, "#FFF4D0");
    sunGrad.addColorStop(0.6, "#FFD700");
    sunGrad.addColorStop(0.85, "#FFA500");
    sunGrad.addColorStop(1, "rgba(255,140,0,0.8)");
    ctx.fillStyle = sunGrad;
    ctx.arc(x,y,85,0,2*Math.PI);
    ctx.fill();
    
    // Güneş lekeleri
    ctx.fillStyle = "rgba(255,200,100,0.4)";
    ctx.beginPath();
    ctx.arc(x-20,y-15,22,0,2*Math.PI);
    ctx.fill();
    ctx.beginPath();
    ctx.arc(x+25,y+10,18,0,2*Math.PI);
    ctx.fill();
    
    // Parlak merkez
    ctx.beginPath();
    const coreGrad = ctx.createRadialGradient(x-10,y-10,0,x,y,35);
    coreGrad.addColorStop(0, "rgba(255,255,255,0.9)");
    coreGrad.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = coreGrad;
    ctx.arc(x-10,y-10,35,0,2*Math.PI);
    ctx.fill();
  }
  
  function drawMoon(){
    const x = canvas.width*0.8;
    const y = canvas.height*0.2;
    
    // Ay hale efekti (çoklu)
    for(let i=5; i>0; i--) {
      ctx.beginPath();
      const haloSize = 70 + i*25;
      const haloGrad = ctx.createRadialGradient(x,y,40,x,y,haloSize);
      haloGrad.addColorStop(0, `rgba(220,220,180,${0.15*i})`);
      haloGrad.addColorStop(1, "rgba(220,220,180,0)");
      ctx.fillStyle = haloGrad;
      ctx.arc(x,y,haloSize,0,2*Math.PI);
      ctx.fill();
    }
    
    // Ana ay cismi
    ctx.beginPath();
    const moonGrad = ctx.createRadialGradient(x-15,y-15,0,x,y,55);
    moonGrad.addColorStop(0, "#FFFEF5");
    moonGrad.addColorStop(0.4, "#F5F3E0");
    moonGrad.addColorStop(0.8, "#E8E4C9");
    moonGrad.addColorStop(1, "#D0CDB0");
    ctx.fillStyle = moonGrad;
    ctx.arc(x,y,55,0,2*Math.PI);
    ctx.fill();
    
    // Ay kraterleri
    ctx.fillStyle = "rgba(120,120,100,0.3)";
    ctx.beginPath(); ctx.arc(x-15,y-12,12,0,2*Math.PI); ctx.fill();
    ctx.beginPath(); ctx.arc(x+18,y+10,16,0,2*Math.PI); ctx.fill();
    ctx.beginPath(); ctx.arc(x-8,y+20,10,0,2*Math.PI); ctx.fill();
    ctx.beginPath(); ctx.arc(x+22,y-18,8,0,2*Math.PI); ctx.fill();
    ctx.beginPath(); ctx.arc(x+5,y-25,7,0,2*Math.PI); ctx.fill();
    
    // Ay gölgesi
    ctx.beginPath();
    ctx.fillStyle = "#2C2C54";
    ctx.arc(x+28,y-14,55,0,2*Math.PI);
    ctx.fill();
  }
  
  function drawStars(){
    stars.forEach(s => {
      // Parıltı animasyonu
      s.a += (Math.random()-0.5)*s.twinkleSpeed;
      s.a = Math.max(0.2, Math.min(1, s.a));
      
      // Ana yıldız
      ctx.fillStyle = `rgba(255,255,255,${s.a})`;
      ctx.beginPath();
      ctx.arc(s.x, s.y, s.r, 0, 2*Math.PI);
      ctx.fill();
      
      // Parlak yıldızlar için ışın efekti
      if(s.a > 0.7 && s.r > 1.5) {
        ctx.strokeStyle = `rgba(255,255,255,${s.a*0.4})`;
        ctx.lineWidth = 1;
        ctx.beginPath();
        const rayLength = s.r * 4;
        ctx.moveTo(s.x-rayLength, s.y); ctx.lineTo(s.x+rayLength, s.y);
        ctx.moveTo(s.x, s.y-rayLength); ctx.lineTo(s.x, s.y+rayLength);
        // Çapraz ışınlar
        const diag = rayLength * 0.7;
        ctx.moveTo(s.x-diag, s.y-diag); ctx.lineTo(s.x+diag, s.y+diag);
        ctx.moveTo(s.x-diag, s.y+diag); ctx.lineTo(s.x+diag, s.y-diag);
        ctx.stroke();
      }
    });
  }
  
  function drawClouds(){
    clouds.forEach(c => {
      ctx.fillStyle = `rgba(255,255,255,${c.opacity})`;
      
      // Gerçekçi çok puflu bulut
      for(let i=0; i<c.puffs; i++) {
        const ratio = i/(c.puffs-1);
        const puffX = c.x + ratio*c.w;
        const puffY = c.y + Math.sin(ratio*Math.PI*2)*c.h*0.25;
        const puffSize = c.w/(c.puffs*0.8) + Math.sin(ratio*Math.PI)*20;
        
        // Puf gölgesi
        ctx.fillStyle = `rgba(200,200,200,${c.opacity*0.3})`;
        ctx.beginPath();
        ctx.ellipse(puffX, puffY+5, puffSize*0.5, puffSize*0.35, 0, 0, 2*Math.PI);
        ctx.fill();
        
        // Ana puf
        ctx.fillStyle = `rgba(255,255,255,${c.opacity})`;
        ctx.beginPath();
        ctx.ellipse(puffX, puffY, puffSize*0.5, puffSize*0.4, 0, 0, 2*Math.PI);
        ctx.fill();
      }
      
      // Bulut hareketi
      c.x += c.s;
      if(c.x - c.w > canvas.width) {
        c.x = -c.w;
        c.y = Math.random()*canvas.height*0.5;
      }
    });
  }
  
  function drawWeatherEffects() {
    // YAĞMUR EFEKTİ
    if(weatherCode.includes('yağmur') || weatherCode.includes('sağanak') || weatherCode.includes('çisel')) {
      raindrops.forEach(drop => {
        // Yağmur damlası çizgisi
        const gradient = ctx.createLinearGradient(drop.x, drop.y, drop.x+drop.xs, drop.y+drop.l);
        gradient.addColorStop(0, `rgba(174,194,224,${drop.opacity*0.5})`);
        gradient.addColorStop(1, `rgba(174,194,224,${drop.opacity})`);
        ctx.strokeStyle = gradient;
        ctx.lineWidth = 2;
        ctx.lineCap = 'round';
        ctx.beginPath();
        ctx.moveTo(drop.x, drop.y);
        ctx.lineTo(drop.x+drop.xs*2, drop.y+drop.l);
        ctx.stroke();
        
        // Damla hareketi
        drop.x += drop.xs;
        drop.y += drop.ys;
        
        // Sınır kontrolü
        if(drop.y > canvas.height) {
          drop.y = -20;
          drop.x = Math.random()*canvas.width;
          // Zemine çarpma efekti
          ctx.fillStyle = `rgba(174,194,224,0.3)`;
          ctx.beginPath();
          ctx.arc(drop.x, canvas.height-5, 3, 0, 2*Math.PI);
          ctx.fill();
        }
        if(drop.x < 0 || drop.x > canvas.width) {
          drop.x = Math.random()*canvas.width;
          drop.y = -20;
        }
      });
      
      // ŞİMŞEK EFEKTİ (fırtına/sağanak için)
      if(weatherCode.includes('fırtın') || weatherCode.includes('sağanak')) {
        lightningTimer++;
        if(lightningTimer > 200 && Math.random() < 0.015) {
          lightningFlash = 20;
          lightningTimer = 0;
        }
        
        if(lightningFlash > 0) {
          // Ekran parlaması
          ctx.fillStyle = `rgba(255,255,255,${lightningFlash/25})`;
          ctx.fillRect(0, 0, canvas.width, canvas.height);
          
          // Şimşek şeridi
          if(lightningFlash > 12) {
            const lx = canvas.width*0.2 + Math.random()*canvas.width*0.6;
            ctx.strokeStyle = `rgba(255,255,220,${lightningFlash/20})`;
            ctx.lineWidth = 4;
            ctx.shadowBlur = 15;
            ctx.shadowColor = 'rgba(255,255,255,0.8)';
            ctx.beginPath();
            ctx.moveTo(lx, 0);
            let currentX = lx;
            let currentY = 0;
            for(let i=0; i<8; i++) {
              currentX += (Math.random()-0.5)*80;
              currentY += canvas.height/8;
              ctx.lineTo(currentX, currentY);
              // Dallanma
              if(i > 2 && Math.random() < 0.3) {
                const branchX = currentX + (Math.random()-0.5)*50;
                const branchY = currentY + canvas.height/16;
                ctx.moveTo(currentX, currentY);
                ctx.lineTo(branchX, branchY);
                ctx.moveTo(currentX, currentY);
              }
            }
            ctx.stroke();
            ctx.shadowBlur = 0;
          }
          lightningFlash--;
        }
      }
    }
    
    // KAR EFEKTİ
    if(weatherCode.includes('kar')) {
      snowflakes.forEach(flake => {
        ctx.save();
        ctx.translate(flake.x, flake.y);
        ctx.rotate(flake.rotation);
        
        // Kar tanesi gövdesi
        ctx.fillStyle = `rgba(255,255,255,${flake.opacity})`;
        ctx.beginPath();
        ctx.arc(0, 0, flake.r, 0, 2*Math.PI);
        ctx.fill();
        
        // Kar tanesi kristal deseni
        ctx.strokeStyle = `rgba(255,255,255,${flake.opacity*0.7})`;
        ctx.lineWidth = 1;
        for(let i=0; i<6; i++) {
          ctx.rotate(Math.PI/3);
          ctx.beginPath();
          ctx.moveTo(0, 0);
          ctx.lineTo(flake.r*2, 0);
          // Yan dallar
          ctx.moveTo(flake.r, 0);
          ctx.lineTo(flake.r*1.3, -flake.r*0.5);
          ctx.moveTo(flake.r, 0);
          ctx.lineTo(flake.r*1.3, flake.r*0.5);
          ctx.stroke();
        }
        ctx.restore();
        
        // Kar hareketi (yavaş salınımlı)
        flake.x += flake.xs + Math.sin(flake.y*0.02)*0.8;
        flake.y += flake.ys;
        flake.rotation += 0.02;
        
        // Sınır kontrolü
        if(flake.y > canvas.height) {
          flake.y = -15;
          flake.x = Math.random()*canvas.width;
        }
        if(flake.x < 0) flake.x = canvas.width;
        if(flake.x > canvas.width) flake.x = 0;
      });
    }
    
    // SİS EFEKTİ
    if(weatherCode.includes('sis')) {
      for(let i=0; i<3; i++) {
        const fogY = canvas.height*0.6 + i*50;
        const fogGrad = ctx.createLinearGradient(0, fogY-30, 0, fogY+30);
        fogGrad.addColorStop(0, "rgba(200,200,200,0)");
        fogGrad.addColorStop(0.5, `rgba(220,220,220,${0.2+i*0.1})`);
        fogGrad.addColorStop(1, "rgba(200,200,200,0)");
        ctx.fillStyle = fogGrad;
        ctx.fillRect(0, fogY-30, canvas.width, 60);
      }
    }
  }
  
  (function loop(){
    requestAnimationFrame(loop);
    drawBG();
  })();
})();
