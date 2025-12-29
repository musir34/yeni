// Yılbaşı Özel Teması - Sinematik, Hediye Dağıtan Noel Baba ve Ultra Gerçekçi Ağaç
(function () {
  const canvas = document.getElementById("weatherCanvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");

  const clamp = (v, min, max) => Math.max(min, Math.min(max, v));
  const rand = (min, max) => min + Math.random() * (max - min);
  const easeInOutCubic = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
  const makeSeededRng = (seed) => {
    // Mulberry32
    let a = (seed >>> 0) || 1;
    return () => {
      a |= 0;
      a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  };

  let snowflakes = [];
  let stars = [];
  let gifts = [];
  let groundSnowHeight = 0; // px
  let snowMass = 0;         // px (zemindeki kar kalınlığı)
  const maxSnowHeight = 80;
  let wind = 0;
  let gust = 0;
  let lastFrameTs = performance.now();

  // Zemin kar yüzeyi: hafif dalgalı (gerçekçi), ama yığın gibi değil
  let groundPhase = 0;
  const groundStepPx = 26;
  let groundSamples = [];

  const smoothstep = (t) => t * t * (3 - 2 * t);
  const hash1 = (i) => {
    // deterministik: treeCache.seed ile bağlı
    const s = Math.sin(i * 127.1 + (treeCache.seed || 1) * 0.001) * 43758.5453123;
    const f = s - Math.floor(s);
    return f * 2 - 1; // [-1,1]
  };
  const valueNoise1D = (x) => {
    const i0 = Math.floor(x);
    const f = x - i0;
    const a = hash1(i0);
    const b = hash1(i0 + 1);
    return a + (b - a) * smoothstep(f);
  };
  const fbm1D = (x) => (0.62 * valueNoise1D(x) + 0.26 * valueNoise1D(x * 2.03 + 11.7) + 0.12 * valueNoise1D(x * 4.01 + 37.1));

  function initGroundSamples() {
    const n = Math.max(8, Math.ceil(canvas.width / groundStepPx) + 2);
    groundSamples = new Array(n).fill(0);
  }

  function groundAmplitudePx() {
    // kar arttıkça yüzey biraz daha şekillensin ama aşırı olmasın
    const k = maxSnowHeight > 0 ? (snowMass / maxSnowHeight) : 0;
    let amp = 1.2 + k * 9.5; // ~1..11 px
    if (plow.active) amp *= 0.35; // küreme sırasında düzleşsin
    return amp;
  }

  function updateGroundSurface(dtMs) {
    if (!groundSamples.length) initGroundSamples();
    const amp = groundAmplitudePx();
    const drift = (wind * 0.0012 + 0.00012) * dtMs;
    groundPhase += drift;

    const n = groundSamples.length;
    // hedef yüzey: düşük frekanslı noise (yumuşak)
    for (let i = 0; i < n; i++) {
      const x = i * groundStepPx;
      const nx = x * 0.012 + groundPhase;
      const target = fbm1D(nx) * amp;
      // low-pass filter: titreme yapmasın
      groundSamples[i] += (target - groundSamples[i]) * (plow.active ? 0.06 : 0.035);
    }
  }

  function getGroundOffsetAtX(x) {
    if (!groundSamples.length) return 0;
    const idx = x / groundStepPx;
    const i0 = Math.floor(idx);
    const t = idx - i0;
    const a = groundSamples[clamp(i0, 0, groundSamples.length - 1)];
    const b = groundSamples[clamp(i0 + 1, 0, groundSamples.length - 1)];
    return a + (b - a) * smoothstep(t);
  }

  function getGroundYAtX(x) {
    const baseY = canvas.height - groundSnowHeight;
    return baseY - getGroundOffsetAtX(x);
  }

  // Hediye atımı: her 5-10 dk'da 1 hediye
  let nextGiftAt = 0;
  function scheduleNextGift(now = Date.now()) {
    nextGiftAt = now + rand(5 * 60 * 1000, 10 * 60 * 1000);
  }

  // Kar küreme: her 10-15 dk'da bir
  const plow = {
    active: false,
    dir: 1,
    x: -300,
    startTs: 0,
    durationMs: 9000
  };
  let nextPlowAt = 0;
  function scheduleNextPlow(now = Date.now()) {
    nextPlowAt = now + rand(10 * 60 * 1000, 15 * 60 * 1000);
  }

  // Ağaç çizimini titremesiz yapmak için cache
  const treeCache = {
    seed: 0,
    sprite: null,
    spriteW: 0,
    spriteH: 0,
    ornaments: [],
    lights: []
  };
  
  // Noel Baba Durumu
  let santa = {
    x: -500,
    y: 100,
    speed: 3,
    direction: 1,
    wobble: 0,
    trail: [],
    state: 'flying', // 'flying', 'waiting'
    waitTimer: 0
  };

  // Ağaç konumu
  let treeX = 0;
  let treeY = 0;

  function resize() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    initSnow();
    initStars();
    initGroundSamples();
    treeX = canvas.width - 220;
    treeY = canvas.height - 50;

    // Cache'i (ağaç) yeniden üret (titremesiz)
    treeCache.seed = (canvas.width * 73856093) ^ (canvas.height * 19349663);
    buildTreeCache();

    // Zamanlayıcıları başlat
    const now = Date.now();
    if (!nextGiftAt) scheduleNextGift(now);
    if (!nextPlowAt) scheduleNextPlow(now);
    
    // Başlangıçta ağacın altına rastgele hediyeler koy
    if(gifts.length === 0) {
        for(let i=0; i<3; i++) {
            gifts.push({
                x: treeX + (Math.random() - 0.5) * 100,
                y: canvas.height - 20,
                vy: 0,
                rotation: (Math.random() - 0.5) * 0.2,
                rotSpeed: 0,
                color: `hsl(${Math.random() * 360}, 70%, 50%)`,
                size: 20 + Math.random() * 20,
                landed: true,
                bury: Math.random() * 5
            });
        }
    }
  }

  function buildTreeCache() {
    const rng = makeSeededRng(treeCache.seed);

    treeCache.ornaments = [];
    treeCache.lights = [];

    // Sprite boyutu (tek sefer çizilecek, sayfada ölçeklenir)
    const spriteW = 280;
    const spriteH = 360;
    const sprite = document.createElement('canvas');
    sprite.width = spriteW;
    sprite.height = spriteH;
    const sctx = sprite.getContext('2d');
    if (!sctx) return;

    // Şeffaf arka plan
    sctx.clearRect(0, 0, spriteW, spriteH);

    const cx = spriteW / 2;
    const baseY = spriteH - 18;
    const treeTopY = 30;

    // Gövde (daha doğal)
    const trunkW = 30;
    const trunkH = 48;
    const trunkGrad = sctx.createLinearGradient(cx - trunkW / 2, baseY - trunkH, cx + trunkW / 2, baseY);
    trunkGrad.addColorStop(0, '#2a1612');
    trunkGrad.addColorStop(0.55, '#5d4037');
    trunkGrad.addColorStop(1, '#1b0f0d');
    sctx.fillStyle = trunkGrad;
    sctx.fillRect(cx - trunkW / 2, baseY - trunkH, trunkW, trunkH);
    sctx.globalAlpha = 0.25;
    sctx.fillStyle = '#000';
    for (let i = 0; i < 10; i++) {
      const x = cx - trunkW / 2 + 3 + (rng() * (trunkW - 6));
      const y = baseY - trunkH + rng() * trunkH;
      sctx.fillRect(x, y, 1, 8 + rng() * 18);
    }
    sctx.globalAlpha = 1;

    // Ağaç formu: çok katmanlı, gradyanlı ve deterministik doku
    const layers = 6;
    for (let li = 0; li < layers; li++) {
      const t = li / (layers - 1);
      const y1 = treeTopY + t * (baseY - treeTopY - 30);
      const y2 = y1 + (46 + t * 58);
      const halfW = 32 + t * 96;

      const g = sctx.createLinearGradient(cx - halfW, y1, cx + halfW, y2);
      g.addColorStop(0, '#0b2f18');
      g.addColorStop(0.55, t < 0.35 ? '#165c2f' : '#1b6a38');
      g.addColorStop(1, '#062010');

      sctx.fillStyle = g;
      sctx.beginPath();
      sctx.moveTo(cx, y1);
      sctx.bezierCurveTo(cx - halfW * 0.35, y1 + 10, cx - halfW, y1 + 22, cx - halfW * 0.95, y2);
      sctx.quadraticCurveTo(cx, y2 + 10, cx + halfW * 0.95, y2);
      sctx.bezierCurveTo(cx + halfW, y1 + 22, cx + halfW * 0.35, y1 + 10, cx, y1);
      sctx.closePath();
      sctx.fill();

      // İç gölge / derinlik
      sctx.globalAlpha = 0.12;
      sctx.fillStyle = '#000';
      sctx.beginPath();
      sctx.ellipse(cx, y1 + (y2 - y1) * 0.62, halfW * 0.45, (y2 - y1) * 0.28, 0, 0, Math.PI * 2);
      sctx.fill();
      sctx.globalAlpha = 1;

      // Doku (iğne hissi) - titremesiz çünkü rng sabit
      const dots = Math.floor(140 + t * 240);
      for (let k = 0; k < dots; k++) {
        const px = cx + (rng() - 0.5) * (halfW * 1.75);
        const py = y1 + rng() * (y2 - y1);
        const alpha = 0.06 + rng() * 0.08;
        const r = 0.5 + rng() * 1.2;
        sctx.globalAlpha = alpha;
        sctx.fillStyle = rng() > 0.6 ? '#2e7d32' : '#43a047';
        sctx.beginPath();
        sctx.arc(px, py, r, 0, Math.PI * 2);
        sctx.fill();
      }
      sctx.globalAlpha = 1;

      // Kar tozu (üst yüzeylere)
      sctx.globalAlpha = 0.12 + (1 - t) * 0.06;
      sctx.fillStyle = '#fff';
      for (let k = 0; k < 38; k++) {
        const px = cx + (rng() - 0.5) * (halfW * 1.4);
        const py = y1 + rng() * (y2 - y1) * 0.38;
        sctx.beginPath();
        sctx.arc(px, py, 0.9 + rng() * 1.2, 0, Math.PI * 2);
        sctx.fill();
      }
      sctx.globalAlpha = 1;
    }

    // Zincir / tinsel (daha "gerçek" metalik)
    const garlandCount = 4;
    for (let i = 0; i < garlandCount; i++) {
      const t = (i + 1) / (garlandCount + 1);
      const yy = treeTopY + t * (baseY - treeTopY - 46);
      const halfW = 40 + t * 110;
      const gg = sctx.createLinearGradient(cx - halfW, yy, cx + halfW, yy + 8);
      gg.addColorStop(0, 'rgba(255,255,255,0)');
      gg.addColorStop(0.2, 'rgba(220,220,220,0.55)');
      gg.addColorStop(0.5, 'rgba(255,215,0,0.65)');
      gg.addColorStop(0.8, 'rgba(220,220,220,0.55)');
      gg.addColorStop(1, 'rgba(255,255,255,0)');
      sctx.strokeStyle = gg;
      sctx.lineWidth = 2.2;
      sctx.beginPath();
      sctx.moveTo(cx - halfW, yy);
      sctx.quadraticCurveTo(cx, yy + 10 + i * 1.5, cx + halfW, yy);
      sctx.stroke();
      // ufak parıltılar
      sctx.globalAlpha = 0.35;
      sctx.fillStyle = '#fff';
      for (let k = 0; k < 10; k++) {
        const px = cx - halfW + rng() * (halfW * 2);
        const py = yy + rng() * 10;
        sctx.beginPath();
        sctx.arc(px, py, 0.7 + rng() * 0.9, 0, Math.PI * 2);
        sctx.fill();
      }
      sctx.globalAlpha = 1;
    }

    // Süsler (daha gerçekçi küre + metal kapak)
    const ornamentColors = [
      { base: '#d50000', hi: '#ff8a80' },
      { base: '#0d47a1', hi: '#82b1ff' },
      { base: '#2e7d32', hi: '#b9f6ca' },
      { base: '#ffd600', hi: '#fff9c4' },
      { base: '#6a1b9a', hi: '#ea80fc' }
    ];
    const ornamentCount = 18;
    for (let i = 0; i < ornamentCount; i++) {
      const t = 0.18 + rng() * 0.74;
      const yy = treeTopY + t * (baseY - treeTopY - 60);
      const halfW = 30 + t * 110;
      const xx = cx + (rng() - 0.5) * (halfW * 1.35);
      const r = 4.5 + rng() * 3.2;
      const palette = ornamentColors[i % ornamentColors.length];
      treeCache.ornaments.push({ x: xx - cx, y: yy - baseY, r, base: palette.base, hi: palette.hi });

      // askı ipi
      sctx.globalAlpha = 0.35;
      sctx.strokeStyle = '#e0e0e0';
      sctx.lineWidth = 1;
      sctx.beginPath();
      sctx.moveTo(xx, yy - r - 6);
      sctx.lineTo(xx, yy - r - 1);
      sctx.stroke();
      sctx.globalAlpha = 1;

      // küre
      const ballGrad = sctx.createRadialGradient(xx - r * 0.35, yy - r * 0.35, 0, xx, yy, r * 1.8);
      ballGrad.addColorStop(0, palette.hi);
      ballGrad.addColorStop(0.25, palette.base);
      ballGrad.addColorStop(1, 'rgba(0,0,0,0.35)');
      sctx.fillStyle = ballGrad;
      sctx.beginPath();
      sctx.arc(xx, yy, r, 0, Math.PI * 2);
      sctx.fill();

      // metal kapak
      const capGrad = sctx.createLinearGradient(xx - r, yy - r - 2, xx + r, yy - r + 3);
      capGrad.addColorStop(0, '#b0bec5');
      capGrad.addColorStop(0.5, '#eceff1');
      capGrad.addColorStop(1, '#90a4ae');
      sctx.fillStyle = capGrad;
      sctx.beginPath();
      sctx.roundRect ? sctx.roundRect(xx - r * 0.55, yy - r - 2, r * 1.1, 4, 1.5) : sctx.rect(xx - r * 0.55, yy - r - 2, r * 1.1, 4);
      sctx.fill();

      // parıltı
      sctx.globalAlpha = 0.55;
      sctx.fillStyle = 'rgba(255,255,255,0.9)';
      sctx.beginPath();
      sctx.ellipse(xx - r * 0.2, yy - r * 0.25, r * 0.22, r * 0.34, 0.6, 0, Math.PI * 2);
      sctx.fill();
      sctx.globalAlpha = 1;
    }

    // Işık noktaları (sprite üstüne çizmeden, ana canvasta animasyonlu parlayacak)
    const lightCount = 42;
    for (let i = 0; i < lightCount; i++) {
      const t = 0.12 + rng() * 0.82;
      const yy = treeTopY + t * (baseY - treeTopY - 60);
      const halfW = 26 + t * 120;
      const xx = cx + (rng() - 0.5) * (halfW * 1.35);
      treeCache.lights.push({ x: xx - cx, y: yy - baseY, phase: i * 0.65 });
    }

    treeCache.sprite = sprite;
    treeCache.spriteW = spriteW;
    treeCache.spriteH = spriteH;
  }

  function initStars() {
    stars = [];
    for (let i = 0; i < 200; i++) {
      stars.push({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height * 0.7,
        size: Math.random() * 1.5,
        opacity: Math.random(),
        twinkleSpeed: 0.005 + Math.random() * 0.02
      });
    }
  }

  function initSnow() {
    snowflakes = [];
    const count = 750; // Daha yoğun ve katmanlı kar
    for (let i = 0; i < count; i++) {
      snowflakes.push({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height,
        z: Math.random() * 3 + 0.5,
        size: Math.random() * 2.5 + 0.5,
        speed: 0.7 + Math.random() * 2.2,
        swing: Math.random() * Math.PI * 2,
        swingSpeed: 0.008 + Math.random() * 0.02,
        opacity: 0.25 + Math.random() * 0.75,
        vx: 0,
        vy: 0
      });
    }
  }

  function drawSky() {
    const gradient = ctx.createLinearGradient(0, 0, 0, canvas.height);
    gradient.addColorStop(0, "#000005");
    gradient.addColorStop(0.3, "#050520");
    gradient.addColorStop(0.7, "#101035");
    gradient.addColorStop(1, "#1a1a4a");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    ctx.fillStyle = "#fff";
    stars.forEach(star => {
      star.opacity += star.twinkleSpeed;
      if (star.opacity > 1 || star.opacity < 0.2) star.twinkleSpeed *= -1;
      ctx.globalAlpha = Math.max(0, Math.min(1, star.opacity));
      ctx.beginPath();
      ctx.arc(star.x, star.y, star.size, 0, Math.PI * 2);
      ctx.fill();
    });
    ctx.globalAlpha = 1;

    // Ay
    const moonX = 100;
    const moonY = 100;
    const moonR = 50;
    
    const glow = ctx.createRadialGradient(moonX, moonY, moonR, moonX, moonY, moonR * 4);
    glow.addColorStop(0, "rgba(255,255,255,0.2)");
    glow.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = glow;
    ctx.beginPath();
    ctx.arc(moonX, moonY, moonR * 4, 0, Math.PI * 2);
    ctx.fill();

    ctx.save();
    ctx.beginPath();
    ctx.arc(moonX, moonY, moonR, 0, Math.PI * 2);
    ctx.clip();
    const moonGrad = ctx.createRadialGradient(moonX - 20, moonY - 20, 0, moonX, moonY, moonR);
    moonGrad.addColorStop(0, "#fff");
    moonGrad.addColorStop(1, "#ddd");
    ctx.fillStyle = moonGrad;
    ctx.fill();
    ctx.fillStyle = "rgba(180,180,190,0.2)";
    [{x: -15, y: -10, r: 10}, {x: 20, y: 15, r: 14}, {x: -10, y: 25, r: 7}].forEach(c => {
        ctx.beginPath(); ctx.arc(moonX + c.x, moonY + c.y, c.r, 0, Math.PI * 2); ctx.fill();
    });
    ctx.restore();
  }

  // Ağaç (yeni: daha gerçekçi sprite + gerçekçi süs)
  function drawTree(x, y) {
    if (!treeCache.sprite) buildTreeCache();
    if (!treeCache.sprite) return;

    const w = treeCache.spriteW;
    const h = treeCache.spriteH;
    const left = x - w / 2;
    const top = y - h;

    // Gölge
    ctx.fillStyle = "rgba(0,0,0,0.28)";
    ctx.beginPath();
    ctx.ellipse(x, y, 95, 18, 0, 0, Math.PI * 2);
    ctx.fill();

    // Sprite ağacı çiz
    ctx.drawImage(treeCache.sprite, left, top);

    // Işıklar (ana canvasta animasyonlu parlayacak)
    const time = Date.now() / 650;
    const colors = ["#ff1744", "#ffea00", "#00b0ff", "#f500ff", "#ff9100", "#ffffff"];
    ctx.save();
    ctx.translate(x, y);
    ctx.globalCompositeOperation = "lighter";
    for (let i = 0; i < treeCache.lights.length; i++) {
      const p = treeCache.lights[i];
      const pulse = 0.35 + 0.65 * (0.5 + 0.5 * Math.sin(time + p.phase));
      const color = colors[i % colors.length];
      ctx.globalAlpha = 0.25 + pulse * 0.75;
      const px = p.x;
      const py = p.y;
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(px, py, 2.2, 0, Math.PI * 2);
      ctx.fill();
      const glow = ctx.createRadialGradient(px, py, 0, px, py, 12);
      glow.addColorStop(0, color);
      glow.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = glow;
      ctx.beginPath();
      ctx.arc(px, py, 12, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = "source-over";
    ctx.restore();

    // Tepe yıldızı (süs)
    const starX = x;
    const starY = top + 18;
    ctx.shadowBlur = 30;
    ctx.shadowColor = "#FFD700";
    ctx.fillStyle = "#FFD700";
    ctx.beginPath();
    for(let i=0; i<5; i++){
        ctx.lineTo(Math.cos((18+i*72)/180*Math.PI)*16 + starX, -Math.sin((18+i*72)/180*Math.PI)*16 + starY);
        ctx.lineTo(Math.cos((54+i*72)/180*Math.PI)*7 + starX, -Math.sin((54+i*72)/180*Math.PI)*7 + starY);
    }
    ctx.fill();
    ctx.shadowBlur = 0;
  }

  // Hediye Kutusu Çizimi
  function drawGift(gift) {
    ctx.save();
    ctx.translate(gift.x, gift.y);
    ctx.rotate(gift.rotation);
    
    const s = gift.size || 20;
    const half = s / 2;

    // Kutu
    ctx.fillStyle = gift.color;
    ctx.fillRect(-half, -half, s, s);
    
    // Şerit (Dikey)
    ctx.fillStyle = "#fff";
    ctx.fillRect(- (s * 0.15), -half, s * 0.3, s);
    // Şerit (Yatay)
    ctx.fillRect(-half, - (s * 0.15), s, s * 0.3);
    
    // Fiyonk
    ctx.fillStyle = "#ffeb3b"; 
    ctx.beginPath();
    ctx.arc(0, -half, s * 0.25, 0, Math.PI * 2);
    ctx.fill();
    
    ctx.restore();
  }

  // Noel Baba
  function drawSanta() {
    const now = Date.now();

    if (santa.state === 'waiting') {
        santa.waitTimer--;
        if (santa.waitTimer <= 0) {
            santa.state = 'flying';
            santa.direction = Math.random() > 0.5 ? 1 : -1;
            santa.x = santa.direction === 1 ? -300 : canvas.width + 300;
            santa.y = 50 + Math.random() * (canvas.height - 300);
        }
        return; 
    }

    santa.x += santa.speed * santa.direction;
    santa.wobble = Math.sin(Date.now() / 200) * 15;
    const currentY = santa.y + santa.wobble;

    // Hediye Atma Mantığı
    // İstek: Her 5-10 dakikada bir 1 hediye (çok cömert olmasın)
    const onScreen = santa.x > -100 && santa.x < canvas.width + 100;
    if (onScreen && now >= nextGiftAt) {
        gifts.push({
            x: santa.x,
            y: currentY + 20,
            vy: 2, 
            rotation: Math.random() * Math.PI,
            rotSpeed: (Math.random() - 0.5) * 0.1,
            color: `hsl(${Math.random() * 360}, 70%, 50%)`,
            size: 15 + Math.random() * 25, // Farklı boyutlar
        landed: false,
        bury: Math.random() * 5
        });
      scheduleNextGift(now);
    }

    if ((santa.direction === 1 && santa.x > canvas.width + 300) || 
        (santa.direction === -1 && santa.x < -300)) {
        santa.state = 'waiting';
        santa.waitTimer = 100 + Math.random() * 200; 
    }

    // Sihirli Toz
    if (Math.random() > 0.2) {
        santa.trail.push({x: santa.x, y: currentY + 15, age: 1, size: Math.random()*3});
    }
    santa.trail.forEach((p, i) => {
        p.age -= 0.02;
        if (p.age <= 0) santa.trail.splice(i, 1);
        ctx.fillStyle = `rgba(255, 220, 100, ${p.age})`;
        ctx.beginPath();
        ctx.arc(p.x - (santa.direction*40) + (Math.random()-0.5)*10, p.y + (Math.random()-0.5)*10, p.size, 0, Math.PI*2);
        ctx.fill();
    });

    ctx.save();
    ctx.translate(santa.x, currentY);
    if (santa.direction === -1) ctx.scale(-1, 1);

    // Kızak
    ctx.beginPath(); ctx.moveTo(-60, 30); ctx.bezierCurveTo(-30, 35, 30, 35, 60, 10);
    ctx.strokeStyle = "#C0C0C0"; ctx.lineWidth = 4; ctx.stroke();
    ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(-40, 32); ctx.lineTo(-40, 10); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(20, 28); ctx.lineTo(20, 10); ctx.stroke();
    ctx.fillStyle = "#8B0000"; ctx.beginPath(); ctx.moveTo(-50, 10); ctx.lineTo(40, 10);
    ctx.quadraticCurveTo(50, 10, 60, -10); ctx.lineTo(-50, -10); ctx.fill();
    ctx.strokeStyle = "#FFD700"; ctx.lineWidth = 2; ctx.stroke();

    // Noel Baba (daha yumuşak gölgelendirme / yüz)
    ctx.fillStyle = "#D32F2F";
    ctx.beginPath();
    ctx.ellipse(-10, -15, 25, 30, 0, 0, Math.PI * 2);
    ctx.fill();

    // Kemer
    ctx.fillStyle = "#111";
    ctx.fillRect(-35, -15, 50, 8);
    ctx.strokeStyle = "#FFD700";
    ctx.lineWidth = 1.5;
    ctx.strokeRect(-20, -15, 10, 8);

    // Yüz (radial gradient ile daha doğal)
    const faceGrad = ctx.createRadialGradient(-8, -44, 2, -5, -40, 18);
    faceGrad.addColorStop(0, "#ffe0c8");
    faceGrad.addColorStop(0.55, "#ffccbc");
    faceGrad.addColorStop(1, "#e6a88f");
    ctx.fillStyle = faceGrad;
    ctx.beginPath();
    ctx.arc(-5, -40, 12, 0, Math.PI * 2);
    ctx.fill();

    // Gözler
    ctx.fillStyle = "rgba(0,0,0,0.9)";
    ctx.beginPath(); ctx.arc(-9, -43, 1.4, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.arc(-2, -42.5, 1.2, 0, Math.PI * 2); ctx.fill();

    // Burun
    ctx.fillStyle = "#e7a18f";
    ctx.beginPath(); ctx.arc(1, -40, 2.4, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "rgba(255,255,255,0.4)";
    ctx.beginPath(); ctx.arc(0.2, -41, 0.9, 0, Math.PI * 2); ctx.fill();

    // Sakal (katmanlı)
    const beardGrad = ctx.createRadialGradient(-8, -28, 3, -10, -26, 26);
    beardGrad.addColorStop(0, "#ffffff");
    beardGrad.addColorStop(1, "rgba(220,220,220,1)");
    ctx.fillStyle = beardGrad;
    ctx.beginPath();
    ctx.moveTo(4, -38);
    ctx.quadraticCurveTo(10, -30, 5, -24);
    ctx.quadraticCurveTo(-2, -18, -12, -24);
    ctx.quadraticCurveTo(-16, -30, -12, -38);
    ctx.closePath();
    ctx.fill();
    ctx.fillStyle = "rgba(255,255,255,0.65)";
    ctx.beginPath(); ctx.ellipse(-2, -32, 5, 2.4, Math.PI/4, 0, Math.PI*2); ctx.fill();

    // Şapka
    ctx.fillStyle = "#D32F2F";
    ctx.beginPath(); ctx.moveTo(-15, -45);
    ctx.quadraticCurveTo(-4, -66, 12, -46);
    ctx.lineTo(-15, -45);
    ctx.fill();
    ctx.beginPath(); ctx.moveTo(-15, -45);
    ctx.quadraticCurveTo(-27, -45, -25, -33);
    ctx.lineTo(-15, -45);
    ctx.fill();
    ctx.fillStyle = "#fff";
    ctx.beginPath(); ctx.arc(-25, -34, 4.2, 0, Math.PI * 2); ctx.fill();
    // Şapkanın kenarı
    if (ctx.roundRect) {
      ctx.beginPath(); ctx.roundRect(-16, -48, 30, 6, 3); ctx.fill();
    } else {
      ctx.fillRect(-16, -48, 30, 6);
    }

    // Torba
    const bagGrad = ctx.createRadialGradient(-44, -14, 3, -40, -10, 26);
    bagGrad.addColorStop(0, "#7b5a3c");
    bagGrad.addColorStop(1, "#4e342e");
    ctx.fillStyle = bagGrad;
    ctx.beginPath(); ctx.arc(-40, -10, 18, 0, Math.PI * 2); ctx.fill();

    // Geyikler (daha dolgun gövde / yumuşak gölge)
    const deerCount = 4;
    for(let i=1; i<=deerCount; i++) {
        const dx = 60 + i * 55;
        const legPhase = (Date.now() / 100) + i;
        ctx.strokeStyle = "rgba(255,255,255,0.3)"; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(40, 0); ctx.lineTo(dx, 5); ctx.stroke();
      const bodyGrad = ctx.createLinearGradient(dx - 5, -5, dx + 35, 20);
      bodyGrad.addColorStop(0, "#6d4c41");
      bodyGrad.addColorStop(0.5, "#8d6e63");
      bodyGrad.addColorStop(1, "#4e342e");
      ctx.fillStyle = bodyGrad;
      ctx.beginPath(); ctx.ellipse(dx + 12, 6, 20, 11, -0.08, 0, Math.PI * 2); ctx.fill();
      ctx.beginPath(); ctx.moveTo(dx + 20, 6); ctx.lineTo(dx + 30, -6); ctx.lineTo(dx + 23, 7); ctx.fill();
        ctx.beginPath(); ctx.ellipse(dx + 32, -8, 9, 7, 0, 0, Math.PI * 2); ctx.fill();
        ctx.beginPath(); ctx.ellipse(dx + 26, -12, 3, 6, -Math.PI/4, 0, Math.PI*2); ctx.fill();
        ctx.fillStyle = "#000"; ctx.beginPath(); ctx.arc(dx + 34, -10, 1, 0, Math.PI*2); ctx.fill();
        ctx.fillStyle = (i === deerCount) ? "#FF0000" : "#222"; ctx.beginPath(); ctx.arc(dx + 40, -7, (i === deerCount) ? 3 : 2, 0, Math.PI * 2); ctx.fill();
        if (i === deerCount) { ctx.shadowBlur = 15; ctx.shadowColor = "red"; ctx.fill(); ctx.shadowBlur = 0; }
        ctx.strokeStyle = "#5D4037"; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.moveTo(dx + 30, -12); ctx.lineTo(dx + 32, -22); ctx.lineTo(dx + 36, -26); ctx.moveTo(dx + 32, -22); ctx.lineTo(dx + 28, -25); ctx.stroke();
        ctx.strokeStyle = "#8D6E63"; ctx.lineWidth = 3; const legSwing = Math.sin(legPhase) * 10;
        ctx.beginPath(); ctx.moveTo(dx, 10); ctx.lineTo(dx - 5 + legSwing, 25); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(dx + 20, 10); ctx.lineTo(dx + 25 - legSwing, 25); ctx.stroke();
    }
    ctx.restore();
  }

  function drawGifts() {
    gifts.forEach((gift, index) => {
        if (!gift.landed) {
            gift.y += gift.vy;
            gift.rotation += gift.rotSpeed;
            
        // Zemin profiline göre iniş
        const gY = getGroundYAtX(gift.x) - 10;
        if (gift.y > gY) {
                gift.landed = true;
                gift.bury = Number.isFinite(gift.bury) ? gift.bury : Math.random() * 5;
            }
        } else {
        // Zemin karı yükselip/alçalınca hediyeyi zemine kilitle
        gift.y = (getGroundYAtX(gift.x) - 10) + (gift.bury || 0);
        }
        drawGift(gift);
        
        if (gifts.length > 80) gifts.shift();
    });
  }

  function drawGround() {
    // İstek: gerçekçi olsun ama yığın gibi değil -> düşük genlikli, yumuşak yüzey
    const baseY = canvas.height - groundSnowHeight;
    const grad = ctx.createLinearGradient(0, baseY - 30, 0, canvas.height);
    grad.addColorStop(0, "#ffffff");
    grad.addColorStop(0.55, "#f2fbff");
    grad.addColorStop(1, "#e8f4ff");
    ctx.fillStyle = grad;

    ctx.beginPath();
    ctx.moveTo(0, canvas.height);
    ctx.lineTo(0, getGroundYAtX(0));
    for (let x = 0; x <= canvas.width; x += groundStepPx) {
      ctx.lineTo(x, getGroundYAtX(x));
    }
    ctx.lineTo(canvas.width, canvas.height);
    ctx.closePath();
    ctx.fill();

    // Tepe çizgisi (çok hafif)
    ctx.globalAlpha = 0.12;
    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(0, getGroundYAtX(0));
    for (let x = 0; x <= canvas.width; x += groundStepPx) {
      ctx.lineTo(x, getGroundYAtX(x));
    }
    ctx.stroke();
    ctx.globalAlpha = 1;

    // Çok hafif doku
    ctx.globalAlpha = 0.05;
    ctx.fillStyle = "#90caf9";
    const t = Date.now() / 2000;
    for (let x = 0; x < canvas.width; x += 24) {
      const yy = getGroundYAtX(x) + 8 + Math.sin(x * 0.02 + t) * 1.2;
      ctx.fillRect(x, yy, 12, 1);
    }
    ctx.globalAlpha = 1;
  }

  function maybeStartPlow(now) {
    if (plow.active) return;
    if (now < nextPlowAt) return;
    plow.active = true;
    plow.startTs = now;
    plow.dir = Math.random() > 0.5 ? 1 : -1;
    plow.x = plow.dir === 1 ? -260 : canvas.width + 260;
    scheduleNextPlow(now);
  }

  function updatePlow(dtMs, now) {
    if (!plow.active) return;
    const t = clamp((now - plow.startTs) / plow.durationMs, 0, 1);
    const eased = easeInOutCubic(t);

    // Karı yumuşak bir hızla azalt (kürüyormuş gibi)
    const clearRatePxPerMs = (maxSnowHeight / plow.durationMs) * 1.2;
    snowMass = Math.max(0, snowMass - clearRatePxPerMs * dtMs);

    // Araç hareketi
    const startX = plow.dir === 1 ? -260 : canvas.width + 260;
    const endX = plow.dir === 1 ? canvas.width + 260 : -260;
    plow.x = startX + (endX - startX) * eased;

    if (t >= 1) {
      plow.active = false;
    }
  }

  function drawPlow() {
    if (!plow.active) return;
    const y = getGroundYAtX(plow.x) - 18;

    ctx.save();
    ctx.translate(plow.x, y);
    if (plow.dir === -1) ctx.scale(-1, 1);

    // Gövde
    ctx.fillStyle = "#455a64";
    ctx.beginPath();
    ctx.roundRect ? ctx.roundRect(-60, -22, 90, 28, 6) : ctx.rect(-60, -22, 90, 28);
    ctx.fill();
    // Kabin
    ctx.fillStyle = "#263238";
    ctx.beginPath();
    ctx.roundRect ? ctx.roundRect(-10, -40, 40, 22, 5) : ctx.rect(-10, -40, 40, 22);
    ctx.fill();
    // Cam
    ctx.fillStyle = "rgba(200,230,255,0.35)";
    ctx.fillRect(-5, -36, 28, 14);

    // Bıçak (kürüyen ön parça)
    ctx.fillStyle = "#ff6f00";
    ctx.beginPath();
    ctx.moveTo(30, -10);
    ctx.lineTo(75, -3);
    ctx.lineTo(75, 10);
    ctx.lineTo(30, 8);
    ctx.closePath();
    ctx.fill();
    ctx.strokeStyle = "rgba(0,0,0,0.25)";
    ctx.stroke();

    // Far
    ctx.fillStyle = "#fffde7";
    ctx.beginPath(); ctx.arc(22, -18, 3.5, 0, Math.PI * 2); ctx.fill();
    ctx.globalAlpha = 0.2;
    ctx.fillStyle = "#fff9c4";
    ctx.beginPath();
    ctx.moveTo(22, -18);
    ctx.lineTo(90, -30);
    ctx.lineTo(90, -6);
    ctx.closePath();
    ctx.fill();
    ctx.globalAlpha = 1;

    // Tekerlekler
    ctx.fillStyle = "#111";
    ctx.beginPath(); ctx.arc(-35, 6, 8, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.arc(5, 6, 8, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#616161";
    ctx.beginPath(); ctx.arc(-35, 6, 4, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.arc(5, 6, 4, 0, Math.PI * 2); ctx.fill();

    // Kar dalgası (kürüyen)
    ctx.globalAlpha = 0.9;
    ctx.fillStyle = "rgba(255,255,255,0.85)";
    ctx.beginPath();
    ctx.ellipse(68, 10, 18, 9, 0.15, 0, Math.PI * 2);
    ctx.fill();
    ctx.globalAlpha = 1;

    ctx.restore();
  }

  function drawSnow(dtMs) {
    // Daha doğal: rüzgar + gust + küçük türbülans
    const now = Date.now();
    gust = 0.8 * Math.sin(now / 2600) + 0.45 * Math.sin(now / 1400);
    wind = 0.65 * Math.sin(now / 3200) + gust;

    let hits = 0;

    snowflakes.sort((a, b) => a.z - b.z);
    for (const flake of snowflakes) {
      const depth = flake.z / 3;
      const scale = 0.55 + depth * 0.85;
      const drawSize = flake.size * scale;

      // Hafif motion blur hissi
      const grad = ctx.createRadialGradient(flake.x, flake.y, 0, flake.x, flake.y, drawSize);
      grad.addColorStop(0, `rgba(255,255,255,${flake.opacity})`);
      grad.addColorStop(1, `rgba(255,255,255,0)`);
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(flake.x, flake.y, drawSize, 0, Math.PI * 2);
      ctx.fill();

      // Fizik
      const sway = Math.sin(flake.swing) * (0.55 + depth);
      const targetVx = (wind * 0.6 + sway) * (0.25 + depth);
      const targetVy = (flake.speed * (0.6 + depth)) * 0.9;
      flake.vx += (targetVx - flake.vx) * 0.03;
      flake.vy += (targetVy - flake.vy) * 0.04;

      flake.x += flake.vx * (dtMs / 16.67);
      flake.y += flake.vy * (dtMs / 16.67);
      flake.swing += flake.swingSpeed * (dtMs / 16.67);

      // Sarmal türbülans
      flake.x += Math.sin((flake.y + now / 6) * 0.01) * 0.25 * depth;

      // Wrap
      if (flake.x < -20) flake.x = canvas.width + 20;
      if (flake.x > canvas.width + 20) flake.x = -20;

      // Zemine temas (performans: sadece zemine yakınken lokal yüzeyi kontrol et)
      const baseY = canvas.height - groundSnowHeight;
      if (flake.y > baseY - 30) {
        const gY = getGroundYAtX(flake.x);
        if (flake.y > gY) {
          flake.y = -10;
          flake.x = Math.random() * canvas.width;
          hits++;
        }
      }
    }

    // Birikim: zemin düz şekilde yükselsin
    // hits ~ frame başına zemine ulaşan kar tanesi; dt ile ölçekleyip yumuşatıyoruz
    const add = hits * (0.0016) * (dtMs / 16.67);
    snowMass = clamp(snowMass + add, 0, maxSnowHeight);
  }

  function animate() {
    const nowPerf = performance.now();
    const dtMs = clamp(nowPerf - lastFrameTs, 0, 50);
    lastFrameTs = nowPerf;

    const now = Date.now();
    maybeStartPlow(now);
    updatePlow(dtMs, now);
    groundSnowHeight = clamp(snowMass, 0, maxSnowHeight);
    updateGroundSurface(dtMs);

    drawSky();
    drawGround();
    drawTree(treeX, treeY - groundSnowHeight);
    drawGifts(); 
    drawSanta();
    drawSnow(dtMs);
    drawPlow();
    
    const grad = ctx.createRadialGradient(canvas.width/2, canvas.height/2, canvas.height/2, canvas.width/2, canvas.height/2, canvas.height);
    grad.addColorStop(0, "rgba(0,0,0,0)"); grad.addColorStop(1, "rgba(0,0,0,0.4)");
    ctx.fillStyle = grad; ctx.fillRect(0,0,canvas.width, canvas.height);

    requestAnimationFrame(animate);
  }

  window.addEventListener("resize", resize);
  resize();
  animate();

  console.log('Gelişmiş Yılbaşı Modu Aktif! 🎁🎄🎅');
})();
