// ══════════════════════════════════════════════════════════════════════════
// ULTRA-GERCEKCI HAVA DURUMU ANIMASYON MOTORU v3
// Her eleman benzersiz, hicbir sey tekrar etmez
// ══════════════════════════════════════════════════════════════════════════
(function () {
  const canvas = document.getElementById("weatherCanvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");

  /* ── Meta ── */
  const meta = (n) => document.querySelector(`meta[name="${n}"]`)?.content || "";
  const weatherDesc = meta("weather-description").toLowerCase();
  const weatherCode = parseInt(meta("weather-code") || "0");
  const cloudPct = parseInt(meta("weather-clouds") || "0");
  const windSpd = parseFloat(meta("weather-wind") || "10");
  const windDir = parseFloat(meta("weather-wind-direction") || "180");

  /* ── Durum ── */
  const isOvercast = weatherCode === 3 || cloudPct >= 90 || weatherDesc.includes("kapalı");
  const isPartly = weatherCode === 2 || (cloudPct >= 50 && cloudPct < 90);
  const isHeavy = weatherDesc.includes("şiddetli") || weatherDesc.includes("sağanak");
  const isRainy = weatherCode >= 51 || weatherDesc.includes("yağmur") || weatherDesc.includes("sağanak");
  const isSnowy = (weatherCode >= 71 && weatherCode <= 86) || weatherDesc.includes("kar");
  const isThunder = weatherCode >= 95;
  const showSun = !isOvercast && !isRainy && !isSnowy;

  /* ── Ruzgar ── */
  let cSpdMul;
  if (windSpd < 5) cSpdMul = 0.02;
  else if (windSpd < 10) cSpdMul = 0.05;
  else if (windSpd < 20) cSpdMul = 0.1;
  else if (windSpd < 35) cSpdMul = 0.2;
  else cSpdMul = 0.4;
  const wAngle = (windDir - 90) * (Math.PI / 180);
  const wX = Math.cos(wAngle) * cSpdMul;
  const wY = Math.sin(wAngle) * cSpdMul * 0.15;
  const rainTilt = Math.min(windSpd / 40, 1) * 0.21;
  const rainSign = Math.cos(wAngle) >= 0 ? 1 : -1;

  /* ── Saat ── */
  function istNow() {
    try { return new Date(new Date().toLocaleString("en-US", { timeZone: "Europe/Istanbul" })); }
    catch { return new Date(); }
  }
  const now = istNow();
  const hour = now.getHours();
  const minute = now.getMinutes();
  const isDay = hour >= 7 && hour < 18;
  const currentH = hour + minute / 60;

  /* ── Ay fazi ── */
  const moonPhase = (() => {
    const c = Math.floor(365.25 * now.getFullYear()) + Math.floor(30.6 * (now.getMonth() + 1)) + now.getDate() - 694039.09;
    const p = c / 29.53;
    return p - Math.floor(p);
  })();

  /* ── Yardimcilar ── */
  const rand = (a, b) => a + Math.random() * (b - a);
  const randInt = (a, b) => Math.floor(rand(a, b + 1));
  const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];
  const lerp = (a, b, t) => a + (b - a) * t;
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

  /* ── Koleksiyonlar ── */
  let clouds = [], raindrops = [], splashes = [], snowflakes = [], stars = [], shootingStars = [];
  let lightning = { active: false, timer: 0, branches: [] };

  // ══════════════════════════════════════════════════════════════
  // BULUT URETECI — Her bulut benzersiz, procedural sekiller
  // ══════════════════════════════════════════════════════════════
  // 8 farkli bulut sablonu + puf varyasyonlari → sonsuz kombinasyon
  const CLOUD_TEMPLATES = [
    // 0: Klasik kabarik cumulus
    (s) => {
      const p = [];
      p.push({ ox: 0, oy: -s * 18, r: s * 32 });
      p.push({ ox: -s * 35, oy: -s * 5, r: s * 28 });
      p.push({ ox: s * 35, oy: -s * 5, r: s * 26 });
      p.push({ ox: -s * 20, oy: s * 5, r: s * 22 });
      p.push({ ox: s * 20, oy: s * 5, r: s * 24 });
      p.push({ ox: 0, oy: s * 8, r: s * 20 });
      return p;
    },
    // 1: Uzun yassı stratus
    (s) => {
      const p = [];
      const w = s * 90;
      for (let i = 0; i < 7; i++) {
        p.push({ ox: -w / 2 + i * (w / 6) + rand(-8, 8), oy: rand(-6, 6), r: s * (15 + rand(0, 12)) });
      }
      return p;
    },
    // 2: Kule seklinde cumulonimbus
    (s) => {
      const p = [];
      p.push({ ox: 0, oy: -s * 35, r: s * 22 });
      p.push({ ox: -s * 10, oy: -s * 22, r: s * 28 });
      p.push({ ox: s * 10, oy: -s * 25, r: s * 25 });
      p.push({ ox: -s * 30, oy: -s * 8, r: s * 24 });
      p.push({ ox: s * 30, oy: -s * 8, r: s * 26 });
      p.push({ ox: 0, oy: s * 2, r: s * 30 });
      p.push({ ox: -s * 18, oy: s * 8, r: s * 20 });
      p.push({ ox: s * 18, oy: s * 8, r: s * 22 });
      return p;
    },
    // 3: Ince cirrus (tuy gibi)
    (s) => {
      const p = [];
      for (let i = 0; i < 10; i++) {
        const t = i / 9;
        p.push({ ox: lerp(-s * 60, s * 60, t) + rand(-5, 5), oy: Math.sin(t * Math.PI) * s * (-8) + rand(-3, 3), r: s * (6 + rand(0, 5)) });
      }
      return p;
    },
    // 4: Cift tepeli deve hoergucu
    (s) => {
      const p = [];
      p.push({ ox: -s * 25, oy: -s * 22, r: s * 28 });
      p.push({ ox: s * 25, oy: -s * 20, r: s * 30 });
      p.push({ ox: 0, oy: -s * 8, r: s * 20 });
      p.push({ ox: -s * 40, oy: s * 2, r: s * 22 });
      p.push({ ox: s * 40, oy: s * 2, r: s * 24 });
      p.push({ ox: 0, oy: s * 8, r: s * 26 });
      return p;
    },
    // 5: Kalp / organik blob
    (s) => {
      const p = [];
      const n = 8 + randInt(0, 4);
      for (let i = 0; i < n; i++) {
        const angle = (i / n) * Math.PI * 2;
        const dist = s * (20 + rand(5, 15));
        p.push({ ox: Math.cos(angle) * dist, oy: Math.sin(angle) * dist * 0.5 - s * 5, r: s * (14 + rand(0, 10)) });
      }
      p.push({ ox: 0, oy: 0, r: s * 25 }); // merkez dolgu
      return p;
    },
    // 6: Ucgen/piramit
    (s) => {
      const p = [];
      p.push({ ox: 0, oy: -s * 30, r: s * 20 });
      p.push({ ox: -s * 20, oy: -s * 15, r: s * 25 });
      p.push({ ox: s * 20, oy: -s * 15, r: s * 23 });
      p.push({ ox: -s * 38, oy: s * 2, r: s * 22 });
      p.push({ ox: 0, oy: s * 5, r: s * 28 });
      p.push({ ox: s * 38, oy: s * 2, r: s * 22 });
      return p;
    },
    // 7: Dalgali / mushroom
    (s) => {
      const p = [];
      p.push({ ox: 0, oy: -s * 25, r: s * 34 });
      p.push({ ox: -s * 30, oy: -s * 10, r: s * 20 });
      p.push({ ox: s * 30, oy: -s * 10, r: s * 20 });
      p.push({ ox: -s * 15, oy: s * 5, r: s * 16 });
      p.push({ ox: s * 15, oy: s * 5, r: s * 16 });
      return p;
    },
  ];

  function makeCloud(forceX) {
    const scale = rand(0.5, 1.1);
    const tmpl = pick(CLOUD_TEMPLATES);
    const puffs = tmpl(scale);
    // Her pufa rastgele pertürbasyon
    puffs.forEach((p) => {
      p.ox += rand(-6, 6);
      p.oy += rand(-4, 4);
      p.r *= rand(0.85, 1.15);
    });
    // Ekstra rastgele puflar
    const extras = randInt(0, 4);
    for (let i = 0; i < extras; i++) {
      puffs.push({
        ox: rand(-50, 50) * scale,
        oy: rand(-20, 15) * scale,
        r: rand(10, 25) * scale,
      });
    }
    return {
      x: forceX !== undefined ? forceX : rand(-300, canvas.width + 300),
      y: rand(18, canvas.height * 0.38),
      scale: 1,
      baseSpeed: rand(0.006, 0.018),
      opacity: isOvercast || isRainy ? rand(0.82, 0.97) : rand(0.35, 0.65),
      puffs,
      // Benzersiz renk varyasyonu
      tint: { r: randInt(-8, 8), g: randInt(-5, 5), b: randInt(-3, 8) },
      // Ic pariltisi
      highlight: rand(0.1, 0.3),
      // Bulut tipleri farkli yuksekliklerde
      depth: rand(0, 1), // 0=uzak, 1=yakin
    };
  }

  function initClouds() {
    clouds = [];
    const count = isOvercast ? randInt(12, 16) : isRainy ? randInt(9, 13) : isPartly ? randInt(7, 11) : randInt(3, 6);
    for (let i = 0; i < count; i++) clouds.push(makeCloud());
    // Derinlige gore sirala (uzak olanlar once cizilir)
    clouds.sort((a, b) => a.depth - b.depth);
  }

  // ══════════════════════════════════════════════════════════════
  // YAGMUR — 5 cesit damla
  // ══════════════════════════════════════════════════════════════
  const RAIN_TYPES = [
    "streak",     // 0: klasik cizgi
    "teardrop",   // 1: damla seklinde (ust kalin, alt sivri)
    "fine",       // 2: ciselek (cok ince kisa)
    "fat",        // 3: iri damla
    "dotted",     // 4: noktali (buharlasiyor gibi)
  ];

  function makeRaindrop() {
    const layer = Math.random();
    const type = isHeavy ? pick([0, 0, 0, 1, 3]) : pick([0, 0, 1, 2, 2, 4]);
    let length, thickness, speed, opacity;

    switch (type) {
      case 0: // streak
        length = 14 + layer * 22;
        thickness = 0.8 + layer * 1.5;
        speed = 11 + layer * 11;
        opacity = 0.15 + layer * 0.4;
        break;
      case 1: // teardrop
        length = 8 + layer * 10;
        thickness = 1.5 + layer * 2;
        speed = 9 + layer * 8;
        opacity = 0.25 + layer * 0.45;
        break;
      case 2: // fine
        length = 4 + layer * 7;
        thickness = 0.4 + layer * 0.4;
        speed = 8 + layer * 6;
        opacity = 0.1 + layer * 0.2;
        break;
      case 3: // fat
        length = 6 + layer * 5;
        thickness = 2.5 + layer * 2;
        speed = 13 + layer * 10;
        opacity = 0.3 + layer * 0.4;
        break;
      case 4: // dotted
        length = 2 + layer * 3;
        thickness = 1 + layer * 1;
        speed = 7 + layer * 5;
        opacity = 0.15 + layer * 0.25;
        break;
    }
    return {
      x: rand(-60, canvas.width + 60),
      y: -rand(0, canvas.height * 1.3),
      speed, length, thickness, opacity, layer, type,
      wobble: rand(0, Math.PI * 2),   // hafif titresim fazı
      wobbleSpd: rand(0.05, 0.15),
    };
  }

  function initRain() {
    raindrops = [];
    const cnt = isHeavy ? randInt(180, 250) : randInt(100, 150);
    for (let i = 0; i < cnt; i++) raindrops.push(makeRaindrop());
  }

  // ══════════════════════════════════════════════════════════════
  // KAR — 6 cesit kar tanesi
  // ══════════════════════════════════════════════════════════════
  const SNOW_TYPES = [
    "star6",      // 0: 6 kollu klasik
    "crystal",    // 1: kristal uclu
    "plate",      // 2: duz tabak (altigen)
    "needle",     // 3: igne seklinde
    "dendrite",   // 4: dallanmali (fractal-imsi)
    "soft",       // 5: yumusak yuvarlak
  ];

  function makeSnowflake() {
    const layer = Math.random();
    const type = randInt(0, 5);
    return {
      x: rand(-20, canvas.width + 20),
      y: -rand(0, canvas.height),
      size: type === 3 ? (1 + layer * 3) : (1.5 + layer * 5.5),
      speed: 0.3 + layer * 1.8,
      swing: rand(0, Math.PI * 2),
      swingSpd: rand(0.006, 0.018),
      swingAmp: rand(0.3, 1.0),
      rot: rand(0, Math.PI * 2),
      rotSpd: (Math.random() - 0.5) * 0.04,
      type,
      opacity: 0.4 + layer * 0.55,
      sparkle: rand(0, Math.PI * 2), // pariltisi
    };
  }

  function initSnow() {
    snowflakes = [];
    const cnt = isHeavy ? randInt(120, 170) : randInt(70, 110);
    for (let i = 0; i < cnt; i++) snowflakes.push(makeSnowflake());
  }

  // ══════════════════════════════════════════════════════════════
  // YILDIZLAR — farkli tipler
  // ══════════════════════════════════════════════════════════════
  function initStars() {
    stars = [];
    for (let i = 0; i < 90; i++) {
      const type = Math.random() < 0.08 ? "giant" : Math.random() < 0.2 ? "colored" : "normal";
      stars.push({
        x: rand(0, canvas.width),
        y: rand(0, canvas.height * 0.65),
        size: type === "giant" ? rand(2, 3.5) : rand(0.3, 2),
        brightness: rand(0.25, 0.85),
        twSpd: rand(0.4, 3),
        twOff: rand(0, Math.PI * 2),
        type,
        color: type === "colored" ? pick(["#ffd4a8", "#a8d4ff", "#ffa8a8", "#a8ffa8", "#ffe4c4"]) : "#ffffff",
      });
    }
    shootingStars = [];
  }

  // ══════════════════════════════════════════════════════════════
  // RESIZE
  // ══════════════════════════════════════════════════════════════
  function resize() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    initClouds();
    if (!isDay) initStars();
    if (isRainy) initRain();
    if (isSnowy) initSnow();
  }

  // ══════════════════════════════════════════════════════════════
  // DRAW: GOKYUZU
  // ══════════════════════════════════════════════════════════════
  function drawSky() {
    const g = ctx.createLinearGradient(0, 0, 0, canvas.height);
    if (!isDay) {
      g.addColorStop(0, "#060614");
      g.addColorStop(0.25, "#0c1230");
      g.addColorStop(0.55, "#162050");
      g.addColorStop(0.8, "#1a237e");
      g.addColorStop(1, "#263260");
    } else if (isOvercast || isRainy) {
      g.addColorStop(0, "#6d8090");
      g.addColorStop(0.3, "#8a9daa");
      g.addColorStop(0.7, "#a8b8c2");
      g.addColorStop(1, "#c5ced5");
    } else if (hour < 9) {
      g.addColorStop(0, "#4a90c8");
      g.addColorStop(0.3, "#7ab8e0");
      g.addColorStop(0.6, "#f0c48a");
      g.addColorStop(0.85, "#e8965a");
      g.addColorStop(1, "#d07040");
    } else if (hour >= 16) {
      g.addColorStop(0, "#3a5a85");
      g.addColorStop(0.2, "#c07050");
      g.addColorStop(0.5, "#e06830");
      g.addColorStop(0.8, "#b03020");
      g.addColorStop(1, "#601520");
    } else {
      g.addColorStop(0, "#1a70b0");
      g.addColorStop(0.3, "#38a0d8");
      g.addColorStop(0.6, "#68c0e8");
      g.addColorStop(0.85, "#90d5f0");
      g.addColorStop(1, "#a8ddf0");
    }
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Ufuk cizgisi: hafif sis/haze
    if (isDay && !isOvercast) {
      const haze = ctx.createLinearGradient(0, canvas.height * 0.7, 0, canvas.height);
      haze.addColorStop(0, "rgba(255,255,255,0)");
      haze.addColorStop(1, "rgba(255,255,255,0.08)");
      ctx.fillStyle = haze;
      ctx.fillRect(0, canvas.height * 0.7, canvas.width, canvas.height * 0.3);
    }
  }

  // ══════════════════════════════════════════════════════════════
  // DRAW: YILDIZLAR
  // ══════════════════════════════════════════════════════════════
  function drawStars() {
    if (isDay || isOvercast) return;
    const t = Date.now() * 0.001;

    stars.forEach((s) => {
      const tw = Math.sin(t * s.twSpd + s.twOff);
      const a = s.brightness * (0.45 + tw * 0.55);
      ctx.globalAlpha = a;
      ctx.fillStyle = s.color;

      if (s.type === "giant") {
        // 4 isinli buyuk yildiz
        const sz = s.size * (1 + tw * 0.15);
        ctx.beginPath();
        ctx.arc(s.x, s.y, sz, 0, Math.PI * 2);
        ctx.fill();
        // Isinlar
        ctx.strokeStyle = s.color;
        ctx.lineWidth = 0.6;
        ctx.globalAlpha = a * 0.4;
        const rl = sz * 5;
        for (let i = 0; i < 4; i++) {
          const ang = (i * Math.PI) / 4 + t * 0.1;
          ctx.beginPath();
          ctx.moveTo(s.x + Math.cos(ang) * sz, s.y + Math.sin(ang) * sz);
          ctx.lineTo(s.x + Math.cos(ang) * rl, s.y + Math.sin(ang) * rl);
          ctx.stroke();
        }
      } else {
        ctx.beginPath();
        ctx.arc(s.x, s.y, s.size, 0, Math.PI * 2);
        ctx.fill();
        if (s.size > 1.4 && a > 0.5) {
          ctx.strokeStyle = s.color;
          ctx.lineWidth = 0.35;
          ctx.globalAlpha = a * 0.2;
          const rl = s.size * 3.5;
          ctx.beginPath();
          ctx.moveTo(s.x - rl, s.y); ctx.lineTo(s.x + rl, s.y);
          ctx.moveTo(s.x, s.y - rl); ctx.lineTo(s.x, s.y + rl);
          ctx.stroke();
        }
      }
    });
    ctx.globalAlpha = 1;

    // Kayan yildizlar
    if (shootingStars.length < 2 && Math.random() < 0.004) {
      shootingStars.push({
        x: rand(canvas.width * 0.1, canvas.width * 0.8),
        y: rand(0, canvas.height * 0.25),
        len: rand(50, 120), speed: rand(10, 18),
        angle: rand(Math.PI * 0.15, Math.PI * 0.4),
        life: 1, decay: rand(0.015, 0.025),
        color: pick(["#fff", "#ffe4c4", "#cce5ff"]),
      });
    }
    for (let i = shootingStars.length - 1; i >= 0; i--) {
      const ss = shootingStars[i];
      ctx.save();
      ctx.translate(ss.x, ss.y);
      ctx.rotate(ss.angle);
      const g = ctx.createLinearGradient(0, 0, -ss.len * ss.life, 0);
      g.addColorStop(0, `rgba(255,255,255,${ss.life})`);
      g.addColorStop(0.4, `rgba(255,255,200,${ss.life * 0.5})`);
      g.addColorStop(1, "rgba(255,255,255,0)");
      ctx.strokeStyle = g;
      ctx.lineWidth = 2.2;
      ctx.lineCap = "round";
      ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(-ss.len * ss.life, 0); ctx.stroke();
      ctx.fillStyle = ss.color;
      ctx.globalAlpha = ss.life;
      ctx.beginPath(); ctx.arc(0, 0, 2.5, 0, Math.PI * 2); ctx.fill();
      ctx.restore();
      ss.x += Math.cos(ss.angle) * ss.speed;
      ss.y += Math.sin(ss.angle) * ss.speed;
      ss.life -= ss.decay;
      if (ss.life <= 0) shootingStars.splice(i, 1);
    }
  }

  // ══════════════════════════════════════════════════════════════
  // DRAW: GUNES — Detayli, katmanli, nefes alan
  // ══════════════════════════════════════════════════════════════
  function drawSun() {
    if (!isDay || !showSun) return;
    const t = Date.now() * 0.001;
    const R = clamp(Math.min(canvas.width, canvas.height) * 0.042, 25, 50);

    // Pozisyon
    const progress = clamp((currentH - 7) / 11, 0, 1);
    const sx = canvas.width * (0.10 + progress * 0.80);
    const topY = canvas.height * 0.09;
    const botY = canvas.height * 0.42;
    const arc = Math.sin(progress * Math.PI);
    const sy = botY - arc * (botY - topY);
    const nearH = progress < 0.15 ? 1 - progress / 0.15 : progress > 0.85 ? (progress - 0.85) / 0.15 : 0;

    // Nabiz: gunes hafifce buyuyup kuculuyor
    const breathe = 1 + Math.sin(t * 0.8) * 0.012;
    const r = R * breathe;

    // 1) En dis atmosferik hale
    const a1 = ctx.createRadialGradient(sx, sy, r, sx, sy, r * 10);
    if (nearH > 0.3) {
      a1.addColorStop(0, `rgba(255,120,50,${0.18 + Math.sin(t) * 0.03})`);
      a1.addColorStop(0.35, "rgba(255,90,30,0.06)");
      a1.addColorStop(1, "rgba(255,50,10,0)");
    } else {
      a1.addColorStop(0, `rgba(255,250,210,${0.16 + Math.sin(t * 1.2) * 0.02})`);
      a1.addColorStop(0.35, "rgba(255,230,140,0.05)");
      a1.addColorStop(1, "rgba(255,200,80,0)");
    }
    ctx.fillStyle = a1;
    ctx.beginPath(); ctx.arc(sx, sy, r * 10, 0, Math.PI * 2); ctx.fill();

    // 2) Orta hale — nefes aliyor
    const a2 = ctx.createRadialGradient(sx, sy, r * 0.8, sx, sy, r * 3.8);
    const haloA = 0.45 + Math.sin(t * 0.6) * 0.08;
    if (nearH > 0) {
      a2.addColorStop(0, `rgba(255,200,140,${haloA})`);
      a2.addColorStop(0.4, `rgba(255,160,90,${haloA * 0.35})`);
      a2.addColorStop(1, "rgba(255,120,60,0)");
    } else {
      a2.addColorStop(0, `rgba(255,255,225,${haloA})`);
      a2.addColorStop(0.4, `rgba(255,240,155,${haloA * 0.3})`);
      a2.addColorStop(1, "rgba(255,200,80,0)");
    }
    ctx.fillStyle = a2;
    ctx.beginPath(); ctx.arc(sx, sy, r * 3.8, 0, Math.PI * 2); ctx.fill();

    // 3) Donen isinlar — 12 ana + 12 ince
    ctx.save();
    ctx.translate(sx, sy);
    ctx.rotate(t * 0.06);
    for (let i = 0; i < 24; i++) {
      ctx.save();
      ctx.rotate((i * Math.PI) / 12);
      const isMain = i % 2 === 0;
      const pulse = 0.25 + Math.sin(t * 1.3 + i * 0.5) * 0.1;
      const rLen = isMain ? r * 5 : r * 3.2;
      const rW = isMain ? 7 : 3;
      const rg = ctx.createLinearGradient(0, -r * 1.2, 0, -rLen);
      rg.addColorStop(0, `rgba(255,250,200,${pulse})`);
      rg.addColorStop(0.4, `rgba(255,240,150,${pulse * 0.25})`);
      rg.addColorStop(1, "rgba(255,220,100,0)");
      ctx.fillStyle = rg;
      ctx.beginPath();
      ctx.moveTo(-rW / 2, -r * 1.2);
      ctx.lineTo(0, -rLen);
      ctx.lineTo(rW / 2, -r * 1.2);
      ctx.closePath();
      ctx.fill();
      ctx.restore();
    }
    ctx.restore();

    // 4) Dis halka
    const rng = ctx.createRadialGradient(sx, sy, r * 0.9, sx, sy, r * 1.15);
    rng.addColorStop(0, "rgba(255,255,255,0)");
    rng.addColorStop(0.5, `rgba(255,255,240,${0.65 + Math.sin(t * 1.5) * 0.1})`);
    rng.addColorStop(1, "rgba(255,240,200,0)");
    ctx.fillStyle = rng;
    ctx.beginPath(); ctx.arc(sx, sy, r * 1.15, 0, Math.PI * 2); ctx.fill();

    // 5) Ana cisim
    ctx.beginPath();
    const sg = ctx.createRadialGradient(sx - r * 0.2, sy - r * 0.2, 0, sx, sy, r);
    if (nearH > 0.3) {
      sg.addColorStop(0, "#FFFAF0"); sg.addColorStop(0.2, "#FFD0A0");
      sg.addColorStop(0.5, "#FF8833"); sg.addColorStop(0.8, "#EE4411"); sg.addColorStop(1, "#BB1100");
    } else if (nearH > 0) {
      sg.addColorStop(0, "#FFFFFF"); sg.addColorStop(0.2, "#FFFACD");
      sg.addColorStop(0.5, "#FFD700"); sg.addColorStop(0.8, "#FFA500"); sg.addColorStop(1, "#FF7700");
    } else {
      sg.addColorStop(0, "#FFFFFF"); sg.addColorStop(0.1, "#FFFFF2");
      sg.addColorStop(0.35, "#FFF59D"); sg.addColorStop(0.65, "#FFEB3B");
      sg.addColorStop(0.85, "#FFB300"); sg.addColorStop(1, "#FF8F00");
    }
    ctx.fillStyle = sg;
    ctx.arc(sx, sy, r, 0, Math.PI * 2); ctx.fill();

    // 6) Gunes lekecikleri (hareketli, farkli boyutlar)
    ctx.globalAlpha = 0.1;
    for (let i = 0; i < 5; i++) {
      const lx = sx + Math.cos(t * 0.3 + i * 1.3) * r * 0.4;
      const ly = sy + Math.sin(t * 0.25 + i * 1.7) * r * 0.35;
      const lr = r * (0.08 + Math.sin(t * 0.7 + i * 2) * 0.03);
      ctx.fillStyle = i % 2 === 0 ? "#FFE082" : "#FFCC33";
      ctx.beginPath(); ctx.arc(lx, ly, lr, 0, Math.PI * 2); ctx.fill();
    }
    ctx.globalAlpha = 1;

    // 7) Merkez parlaklik
    const core = ctx.createRadialGradient(sx - r * 0.1, sy - r * 0.1, 0, sx, sy, r * 0.4);
    core.addColorStop(0, "rgba(255,255,255,0.9)");
    core.addColorStop(0.5, "rgba(255,255,255,0.2)");
    core.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = core;
    ctx.beginPath(); ctx.arc(sx, sy, r * 0.4, 0, Math.PI * 2); ctx.fill();

    // 8) Lens flare (farkli her seferinde)
    const cx2 = canvas.width / 2, cy2 = canvas.height / 2;
    const dx = cx2 - sx, dy = cy2 - sy;
    const flares = [
      { o: 0.25, c: `rgba(255,190,90,${0.1 + Math.sin(t) * 0.03})`, s: 12 },
      { o: 0.45, c: `rgba(90,180,255,${0.07 + Math.sin(t * 1.3) * 0.02})`, s: 20 },
      { o: 0.7, c: `rgba(255,140,40,${0.05 + Math.sin(t * 0.8) * 0.02})`, s: 16 },
      { o: 1.1, c: `rgba(140,255,190,${0.04})`, s: 28 },
      { o: 1.5, c: "rgba(255,255,255,0.025)", s: 35 },
    ];
    flares.forEach((f) => {
      const fx = sx + dx * f.o, fy = sy + dy * f.o;
      const fg = ctx.createRadialGradient(fx, fy, 0, fx, fy, f.s);
      fg.addColorStop(0, f.c); fg.addColorStop(1, "rgba(255,255,255,0)");
      ctx.fillStyle = fg;
      ctx.beginPath(); ctx.arc(fx, fy, f.s, 0, Math.PI * 2); ctx.fill();
    });
  }

  // ══════════════════════════════════════════════════════════════
  // DRAW: AY — Detayli, kraterli, hale cizgili
  // ══════════════════════════════════════════════════════════════
  function drawMoon() {
    if (isDay || isOvercast) return;
    const t = Date.now() * 0.001;
    const mx = canvas.width * 0.83;
    const my = canvas.height * 0.16;
    const r = 28;

    // Dis hale — nefes aliyor
    const gA = 0.15 + Math.sin(t * 0.4) * 0.04;
    const g1 = ctx.createRadialGradient(mx, my, r, mx, my, r * 4);
    g1.addColorStop(0, `rgba(220,230,255,${gA})`);
    g1.addColorStop(0.4, `rgba(180,200,240,${gA * 0.4})`);
    g1.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = g1;
    ctx.beginPath(); ctx.arc(mx, my, r * 4, 0, Math.PI * 2); ctx.fill();

    // Ince hale halkalari
    ctx.strokeStyle = `rgba(200,215,240,${0.06 + Math.sin(t * 0.3) * 0.02})`;
    ctx.lineWidth = 0.5;
    for (let i = 1; i <= 3; i++) {
      ctx.beginPath(); ctx.arc(mx, my, r * (1.4 + i * 0.6), 0, Math.PI * 2); ctx.stroke();
    }

    // Ay yüzeyi
    ctx.save();
    ctx.beginPath(); ctx.arc(mx, my, r, 0, Math.PI * 2); ctx.clip();

    const mg = ctx.createRadialGradient(mx - 4, my - 4, 0, mx, my, r);
    mg.addColorStop(0, "#FFFFF8"); mg.addColorStop(0.4, "#F2F0DC"); mg.addColorStop(1, "#D8D4BC");
    ctx.fillStyle = mg;
    ctx.fillRect(mx - r, my - r, r * 2, r * 2);

    // Kraterler — farkli boyut ve derinlik
    const craters = [
      { x: -9, y: -10, r: 7.5, d: 0.25 },
      { x: 12, y: 4, r: 5.5, d: 0.2 },
      { x: -5, y: 12, r: 6.5, d: 0.22 },
      { x: 9, y: -9, r: 4, d: 0.18 },
      { x: 2, y: 1, r: 3, d: 0.15 },
      { x: -13, y: 3, r: 3.5, d: 0.12 },
      { x: 6, y: -16, r: 3, d: 0.1 },
      { x: -3, y: -5, r: 2, d: 0.1 },
      { x: 14, y: -3, r: 2.5, d: 0.12 },
    ];
    craters.forEach((c) => {
      // Cukur
      ctx.fillStyle = `rgba(160,155,140,${c.d})`;
      ctx.beginPath(); ctx.arc(mx + c.x, my + c.y, c.r, 0, Math.PI * 2); ctx.fill();
      // Kenar (aydinlik)
      ctx.strokeStyle = `rgba(255,255,240,${c.d * 0.5})`;
      ctx.lineWidth = 0.4;
      ctx.beginPath(); ctx.arc(mx + c.x - 0.3, my + c.y - 0.3, c.r, -0.5, Math.PI * 0.8); ctx.stroke();
      // Golge (karartma)
      ctx.fillStyle = `rgba(120,115,100,${c.d * 0.4})`;
      ctx.beginPath(); ctx.arc(mx + c.x + 0.8, my + c.y + 0.8, c.r * 0.7, 0, Math.PI * 2); ctx.fill();
    });

    // Mare (deniz) alanlari — koyu lekeler
    ctx.fillStyle = "rgba(155,150,135,0.08)";
    ctx.beginPath(); ctx.ellipse(mx - 5, my + 3, 12, 8, 0.3, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.ellipse(mx + 8, my - 6, 8, 5, -0.4, 0, Math.PI * 2); ctx.fill();
    ctx.restore();

    // Faz golgesi
    ctx.save();
    ctx.beginPath(); ctx.arc(mx, my, r, 0, Math.PI * 2); ctx.clip();
    const pAngle = moonPhase * Math.PI * 2;
    const shX = Math.cos(pAngle) * r * 2;
    ctx.fillStyle = "rgba(6,6,20,0.93)";
    ctx.beginPath(); ctx.ellipse(mx + shX, my, Math.abs(shX) || 0.1, r, 0, 0, Math.PI * 2); ctx.fill();
    ctx.restore();
  }

  // ══════════════════════════════════════════════════════════════
  // DRAW: BULUTLAR
  // ══════════════════════════════════════════════════════════════
  function drawCloud(c) {
    ctx.save();
    ctx.translate(c.x, c.y);

    const depthFade = 0.6 + c.depth * 0.4; // uzak bulutlar daha soluk
    const baseR = isOvercast || isRainy ? 190 : 248;
    const R = clamp(baseR + c.tint.r, 0, 255);
    const G = clamp(baseR + c.tint.g - 3, 0, 255);
    const B = clamp(baseR + c.tint.b, 0, 255);
    const shadowR = isOvercast || isRainy ? 148 : 210;

    // Alt golge
    ctx.fillStyle = `rgba(${shadowR},${shadowR + 5},${shadowR + 10},${c.opacity * 0.25 * depthFade})`;
    ctx.beginPath(); ctx.ellipse(0, 22, 85, 16, 0, 0, Math.PI * 2); ctx.fill();

    // Ana puflar
    ctx.fillStyle = `rgba(${R},${G},${B},${c.opacity * depthFade})`;
    c.puffs.forEach((p) => {
      ctx.beginPath(); ctx.arc(p.ox, p.oy, p.r, 0, Math.PI * 2); ctx.fill();
    });

    // Ust highlight (isik vurdu)
    if (!isOvercast && !isRainy && isDay) {
      ctx.fillStyle = `rgba(255,255,255,${c.highlight * c.opacity * depthFade})`;
      c.puffs.forEach((p) => {
        if (p.oy < 2) {
          ctx.beginPath(); ctx.arc(p.ox - 2, p.oy - p.r * 0.25, p.r * 0.5, 0, Math.PI * 2); ctx.fill();
        }
      });
    }

    // Alt kenar koyu cizgi (derinlik)
    if (isOvercast || isRainy) {
      ctx.fillStyle = `rgba(${shadowR - 20},${shadowR - 15},${shadowR - 10},${c.opacity * 0.2 * depthFade})`;
      c.puffs.forEach((p) => {
        if (p.oy > -5) {
          ctx.beginPath(); ctx.arc(p.ox, p.oy + p.r * 0.3, p.r * 0.7, 0, Math.PI * 2); ctx.fill();
        }
      });
    }
    ctx.restore();
  }

  function drawClouds() {
    clouds.forEach((c) => {
      drawCloud(c);
      c.x += c.baseSpeed + wX;
      c.y += wY * 0.4;
      if (c.x > canvas.width + 300) { c.x = -300; c.y = rand(18, canvas.height * 0.38); }
      if (c.x < -350) { c.x = canvas.width + 280; }
      c.y = clamp(c.y, 12, canvas.height * 0.43);
    });
  }

  // ══════════════════════════════════════════════════════════════
  // DRAW: YAGMUR — 5 farkli damla tipi
  // ══════════════════════════════════════════════════════════════
  function drawRain() {
    if (!isRainy) return;
    ctx.lineCap = "round";

    raindrops.forEach((d) => {
      const tiltX = Math.sin(rainTilt * rainSign);
      const tiltY = Math.cos(rainTilt);
      // Hafif wobble
      const wb = Math.sin(d.wobble) * 0.3;
      d.wobble += d.wobbleSpd;

      switch (d.type) {
        case 0: { // streak — klasik cizgi
          const ex = d.x + tiltX * d.length;
          const ey = d.y + tiltY * d.length;
          const g = ctx.createLinearGradient(d.x, d.y, ex, ey);
          g.addColorStop(0, `rgba(185,210,240,${d.opacity * 0.15})`);
          g.addColorStop(0.4, `rgba(210,225,248,${d.opacity})`);
          g.addColorStop(1, `rgba(230,240,255,${d.opacity * 0.3})`);
          ctx.strokeStyle = g; ctx.lineWidth = d.thickness;
          ctx.beginPath(); ctx.moveTo(d.x, d.y); ctx.lineTo(ex, ey); ctx.stroke();
          break;
        }
        case 1: { // teardrop — damla seklinde
          ctx.save();
          ctx.translate(d.x, d.y);
          ctx.rotate(rainTilt * rainSign);
          const dg = ctx.createRadialGradient(0, -d.length * 0.3, 0, 0, 0, d.length * 0.6);
          dg.addColorStop(0, `rgba(210,225,250,${d.opacity})`);
          dg.addColorStop(1, `rgba(190,210,240,${d.opacity * 0.3})`);
          ctx.fillStyle = dg;
          ctx.beginPath();
          ctx.moveTo(0, -d.length);
          ctx.bezierCurveTo(-d.thickness * 1.2, -d.length * 0.4, -d.thickness * 1.2, d.length * 0.2, 0, d.length * 0.3);
          ctx.bezierCurveTo(d.thickness * 1.2, d.length * 0.2, d.thickness * 1.2, -d.length * 0.4, 0, -d.length);
          ctx.fill();
          ctx.restore();
          break;
        }
        case 2: { // fine — ciselek
          ctx.strokeStyle = `rgba(200,220,248,${d.opacity})`;
          ctx.lineWidth = d.thickness;
          const ex = d.x + tiltX * d.length;
          const ey = d.y + tiltY * d.length;
          ctx.beginPath(); ctx.moveTo(d.x, d.y); ctx.lineTo(ex, ey); ctx.stroke();
          break;
        }
        case 3: { // fat — iri damla
          ctx.save();
          ctx.translate(d.x, d.y);
          const fg = ctx.createRadialGradient(0, 0, 0, 0, 0, d.thickness);
          fg.addColorStop(0, `rgba(200,220,250,${d.opacity})`);
          fg.addColorStop(0.6, `rgba(180,210,245,${d.opacity * 0.6})`);
          fg.addColorStop(1, `rgba(160,200,240,${d.opacity * 0.1})`);
          ctx.fillStyle = fg;
          ctx.beginPath(); ctx.ellipse(0, 0, d.thickness, d.thickness * 1.4, rainTilt * rainSign, 0, Math.PI * 2); ctx.fill();
          ctx.restore();
          break;
        }
        case 4: { // dotted — kucuk noktalar dizisi
          ctx.fillStyle = `rgba(210,225,248,${d.opacity})`;
          for (let i = 0; i < 3; i++) {
            ctx.beginPath();
            ctx.arc(d.x + tiltX * i * 4, d.y + tiltY * i * 4, d.thickness * 0.5, 0, Math.PI * 2);
            ctx.fill();
          }
          break;
        }
      }

      // Hareket
      d.y += d.speed;
      d.x += tiltX * d.speed * 0.15 + wb;

      if (d.y > canvas.height - 3) {
        // Sicrama
        if (d.type !== 2 && Math.random() < 0.35) {
          const splType = d.type === 3 ? "big" : d.type === 1 ? "crown" : "ring";
          splashes.push({ x: d.x, y: canvas.height - 2, life: 1, size: 1.5 + d.layer * 3, type: splType });
        }
        Object.assign(d, makeRaindrop());
        d.y = -d.length - rand(0, 80);
      }
    });

    // Sicramalar — 3 cesit
    for (let i = splashes.length - 1; i >= 0; i--) {
      const sp = splashes[i];
      const prog = 1 - sp.life;
      ctx.globalAlpha = sp.life * 0.6;

      if (sp.type === "ring") {
        ctx.strokeStyle = "rgba(215,230,250,0.7)";
        ctx.lineWidth = 0.7;
        ctx.beginPath(); ctx.arc(sp.x, sp.y, prog * sp.size * 5 + 1, 0, Math.PI * 2); ctx.stroke();
      } else if (sp.type === "crown") {
        // Tac seklinde 3-4 damlacik havaya sicratiyor
        ctx.fillStyle = "rgba(215,230,250,0.7)";
        for (let j = 0; j < 4; j++) {
          const angle = -Math.PI * 0.15 - j * (Math.PI * 0.7 / 3);
          const dist = prog * sp.size * 5;
          const upH = sp.life * sp.size * 4;
          ctx.beginPath();
          ctx.arc(sp.x + Math.cos(angle) * dist, sp.y - upH + Math.sin(angle) * dist * 0.3, 0.7 + sp.life * 0.5, 0, Math.PI * 2);
          ctx.fill();
        }
      } else { // big
        ctx.strokeStyle = "rgba(210,225,248,0.6)";
        ctx.lineWidth = 1;
        ctx.beginPath(); ctx.arc(sp.x, sp.y, prog * sp.size * 7 + 2, Math.PI, Math.PI * 2); ctx.stroke();
        ctx.fillStyle = "rgba(215,230,250,0.5)";
        const spread = prog * sp.size * 6;
        const upH = sp.life * sp.size * 5;
        ctx.beginPath(); ctx.arc(sp.x - spread, sp.y - upH, 1, 0, Math.PI * 2); ctx.fill();
        ctx.beginPath(); ctx.arc(sp.x + spread, sp.y - upH, 1, 0, Math.PI * 2); ctx.fill();
        ctx.beginPath(); ctx.arc(sp.x, sp.y - upH * 1.3, 0.8, 0, Math.PI * 2); ctx.fill();
      }
      sp.life -= 0.035;
      if (sp.life <= 0) splashes.splice(i, 1);
    }
    ctx.globalAlpha = 1;
  }

  // ══════════════════════════════════════════════════════════════
  // DRAW: KAR — 6 farkli tane tipi
  // ══════════════════════════════════════════════════════════════
  function drawSnow() {
    if (!isSnowy) return;
    const t = Date.now() * 0.001;

    snowflakes.forEach((f) => {
      ctx.save();
      ctx.translate(f.x, f.y);
      ctx.rotate(f.rot);
      ctx.globalAlpha = f.opacity;

      // Parlama efekti (bazi tanelerde)
      const sparkle = 0.7 + Math.sin(t * 2 + f.sparkle) * 0.3;

      switch (f.type) {
        case 0: drawFlake6Arm(f.size, sparkle); break;
        case 1: drawFlakeCrystal(f.size, sparkle); break;
        case 2: drawFlakePlate(f.size, sparkle); break;
        case 3: drawFlakeNeedle(f.size, sparkle); break;
        case 4: drawFlakeDendrite(f.size, sparkle); break;
        case 5: drawFlakeSoft(f.size, sparkle); break;
      }
      ctx.restore();

      f.y += f.speed;
      f.swing += f.swingSpd;
      f.x += Math.sin(f.swing) * f.swingAmp + wX * windSpd * 0.06;
      f.rot += f.rotSpd;

      if (f.y > canvas.height + f.size * 2) { f.y = -f.size * 2; f.x = rand(-20, canvas.width + 20); }
      if (f.x > canvas.width + 30) f.x = -30;
      if (f.x < -30) f.x = canvas.width + 30;
    });
  }

  // 0: 6 kollu klasik + dallar
  function drawFlake6Arm(sz, sp) {
    ctx.strokeStyle = `rgba(255,255,255,${sp})`;
    ctx.lineWidth = 0.7;
    ctx.lineCap = "round";
    for (let i = 0; i < 6; i++) {
      ctx.save(); ctx.rotate((i * Math.PI) / 3);
      ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(0, -sz); ctx.stroke();
      // 2 cift yan dal
      ctx.beginPath();
      ctx.moveTo(0, -sz * 0.35); ctx.lineTo(-sz * 0.22, -sz * 0.52);
      ctx.moveTo(0, -sz * 0.35); ctx.lineTo(sz * 0.22, -sz * 0.52);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(0, -sz * 0.65); ctx.lineTo(-sz * 0.15, -sz * 0.78);
      ctx.moveTo(0, -sz * 0.65); ctx.lineTo(sz * 0.15, -sz * 0.78);
      ctx.stroke();
      ctx.restore();
    }
  }

  // 1: Kristal uclu
  function drawFlakeCrystal(sz, sp) {
    ctx.strokeStyle = `rgba(255,255,255,${sp})`;
    ctx.lineWidth = 1;
    ctx.lineCap = "round";
    for (let i = 0; i < 6; i++) {
      ctx.save(); ctx.rotate((i * Math.PI) / 3);
      ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(0, -sz); ctx.stroke();
      // Uc baklava dilimi
      ctx.beginPath();
      ctx.moveTo(0, -sz); ctx.lineTo(-sz * 0.15, -sz * 1.1); ctx.lineTo(0, -sz * 1.2);
      ctx.lineTo(sz * 0.15, -sz * 1.1); ctx.closePath();
      ctx.fillStyle = `rgba(230,240,255,${sp * 0.3})`;
      ctx.fill(); ctx.stroke();
      ctx.restore();
    }
    // Merkez
    ctx.fillStyle = `rgba(255,255,255,${sp * 0.6})`;
    ctx.beginPath(); ctx.arc(0, 0, sz * 0.1, 0, Math.PI * 2); ctx.fill();
  }

  // 2: Duz altigen tabak
  function drawFlakePlate(sz, sp) {
    ctx.strokeStyle = `rgba(255,255,255,${sp * 0.8})`;
    ctx.lineWidth = 0.6;
    // Dis altigen
    ctx.beginPath();
    for (let i = 0; i < 6; i++) {
      const a = (i * Math.PI) / 3 - Math.PI / 6;
      const px = Math.cos(a) * sz, py = Math.sin(a) * sz;
      i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py);
    }
    ctx.closePath(); ctx.stroke();
    // Ic altigen
    ctx.beginPath();
    for (let i = 0; i < 6; i++) {
      const a = (i * Math.PI) / 3 - Math.PI / 6;
      const px = Math.cos(a) * sz * 0.55, py = Math.sin(a) * sz * 0.55;
      i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py);
    }
    ctx.closePath();
    ctx.fillStyle = `rgba(230,240,255,${sp * 0.12})`;
    ctx.fill(); ctx.stroke();
    // Cizgiler
    for (let i = 0; i < 6; i++) {
      const a = (i * Math.PI) / 3;
      ctx.beginPath(); ctx.moveTo(0, 0);
      ctx.lineTo(Math.cos(a) * sz * 0.55, Math.sin(a) * sz * 0.55);
      ctx.stroke();
    }
  }

  // 3: Igne (uzun ince)
  function drawFlakeNeedle(sz, sp) {
    ctx.strokeStyle = `rgba(255,255,255,${sp})`;
    ctx.lineWidth = 0.8;
    ctx.lineCap = "round";
    ctx.beginPath(); ctx.moveTo(0, -sz * 1.5); ctx.lineTo(0, sz * 1.5); ctx.stroke();
    // Uc parlaklik
    ctx.fillStyle = `rgba(255,255,255,${sp * 0.6})`;
    ctx.beginPath(); ctx.arc(0, -sz * 1.5, 0.6, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.arc(0, sz * 1.5, 0.6, 0, Math.PI * 2); ctx.fill();
  }

  // 4: Dendrit (dallanmali, fractal-imsi)
  function drawFlakeDendrite(sz, sp) {
    ctx.strokeStyle = `rgba(255,255,255,${sp})`;
    ctx.lineWidth = 0.6;
    ctx.lineCap = "round";
    for (let i = 0; i < 6; i++) {
      ctx.save(); ctx.rotate((i * Math.PI) / 3);
      // Ana kol
      ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(0, -sz); ctx.stroke();
      // 3 cift dal
      for (let d = 0; d < 3; d++) {
        const p = 0.3 + d * 0.25;
        const bLen = sz * (0.25 - d * 0.05);
        ctx.beginPath();
        ctx.moveTo(0, -sz * p); ctx.lineTo(-bLen, -sz * p - bLen * 0.5);
        ctx.moveTo(0, -sz * p); ctx.lineTo(bLen, -sz * p - bLen * 0.5);
        ctx.stroke();
        // Alt-dallar
        if (d < 2) {
          const sLen = bLen * 0.5;
          ctx.beginPath();
          ctx.moveTo(-bLen * 0.6, -sz * p - bLen * 0.3);
          ctx.lineTo(-bLen * 0.6 - sLen * 0.5, -sz * p - bLen * 0.3 - sLen * 0.4);
          ctx.moveTo(bLen * 0.6, -sz * p - bLen * 0.3);
          ctx.lineTo(bLen * 0.6 + sLen * 0.5, -sz * p - bLen * 0.3 - sLen * 0.4);
          ctx.stroke();
        }
      }
      ctx.restore();
    }
  }

  // 5: Yumusak yuvarlak
  function drawFlakeSoft(sz, sp) {
    const g = ctx.createRadialGradient(0, 0, 0, 0, 0, sz * 0.55);
    g.addColorStop(0, `rgba(255,255,255,${sp * 0.9})`);
    g.addColorStop(0.6, `rgba(235,240,255,${sp * 0.4})`);
    g.addColorStop(1, `rgba(220,230,250,0)`);
    ctx.fillStyle = g;
    ctx.beginPath(); ctx.arc(0, 0, sz * 0.55, 0, Math.PI * 2); ctx.fill();
  }

  // ══════════════════════════════════════════════════════════════
  // DRAW: YILDIRIM
  // ══════════════════════════════════════════════════════════════
  function drawLightning() {
    if (!isThunder) return;
    if (!lightning.active && Math.random() < 0.003) {
      lightning.active = true;
      lightning.timer = randInt(5, 9);
      const sx = rand(canvas.width * 0.15, canvas.width * 0.85);
      lightning.branches = genBolt(sx, 0, canvas.height * rand(0.45, 0.75));
    }
    if (!lightning.active) return;

    if (lightning.timer > 4) {
      ctx.fillStyle = "rgba(255,255,255,0.12)";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
    }
    const alpha = lightning.timer / 9;
    ctx.strokeStyle = `rgba(200,218,255,${alpha})`;
    ctx.lineWidth = 2.5;
    ctx.shadowColor = `rgba(150,180,255,${alpha * 0.8})`;
    ctx.shadowBlur = 18;
    ctx.lineCap = "round"; ctx.lineJoin = "round";

    lightning.branches.forEach((b) => {
      ctx.beginPath(); ctx.moveTo(b[0].x, b[0].y);
      for (let k = 1; k < b.length; k++) ctx.lineTo(b[k].x, b[k].y);
      ctx.stroke();
    });
    ctx.shadowBlur = 0;
    lightning.timer--;
    if (lightning.timer <= 0) lightning.active = false;
  }

  function genBolt(sx, sy, ey) {
    const branches = [];
    const main = []; let cx = sx, cy = sy;
    const segs = randInt(10, 18);
    const stepY = (ey - sy) / segs;
    for (let i = 0; i <= segs; i++) {
      main.push({ x: cx, y: cy });
      cx += rand(-55, 55); cy += stepY;
      if (i > 2 && i < segs - 1 && Math.random() < 0.4) {
        const sub = []; let bx = cx, by = cy;
        for (let j = 0; j < randInt(3, 6); j++) {
          sub.push({ x: bx, y: by });
          bx += rand(-35, 35) + (Math.random() > 0.5 ? 12 : -12);
          by += stepY * 0.65;
        }
        branches.push(sub);
      }
    }
    branches.unshift(main);
    return branches;
  }

  // ══════════════════════════════════════════════════════════════
  // ANA DONGU
  // ══════════════════════════════════════════════════════════════
  function animate() {
    drawSky();
    drawStars();
    drawSun();
    drawMoon();
    drawClouds();
    drawRain();
    drawSnow();
    drawLightning();
    requestAnimationFrame(animate);
  }

  window.addEventListener("resize", resize);
  resize();
  animate();

  console.log("[WEATHER] Kod:", weatherCode, "| Bulut:", cloudPct + "%", "| Ruzgar:", windSpd, "km/h", "| Gunes:", showSun, "| Saat:", hour + ":" + minute);
})();
