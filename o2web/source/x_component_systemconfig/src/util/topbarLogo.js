/**
 * 顶栏 Logo 蓝底适配 —— 前端 Canvas 合成工具（2026-10-17）
 * ------------------------------------------------------------------
 * 背景：门户顶栏「中国复合材料工业协会」不是 DOM 文本，而是烤在 logo.png
 *       位图内（纯黑）。蓝底上黑字不可读；红圈直接贴蓝底观感差。
 *       解决方案：从品牌 Logo 中切出【左侧徽标】，垫一张白色圆角卡片，
 *       右侧用白色粗体字渲染组织名称，合成新位图 logo_topbar.png。
 *
 * 本文件算法 1:1 复刻仓库 tools/o2_portal_topbar_logo_white.py 的 Python 逻辑
 * （已渲染级验证 5/5 PASS），保证 GUI 生成的成品与离线工具完全一致。
 *
 * 关键约定：
 *   - 顶栏 Image 模块已永久指向 /custom_brand/logo_topbar.png（库内锚点替换，
 *     非 designer 保存，不破坏 relatedScriptMap），故本工具只负责【生成+部署】，
 *     不触碰门户设计；开关关闭时透传原 Logo（白底卡片消失）。
 *   - 同域加载 → canvas 不被污染 → toBlob 可用（无需 crossOrigin 网络）。
 */

const ORIGIN = (typeof window !== 'undefined' && window.location)
  ? (window.location.protocol + '//' + window.location.host)
  : 'http://127.0.0.1:9090';

function canvasToBlob(canvas) {
  return new Promise((res) => canvas.toBlob(res, 'image/png'));
}

function loadImg(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = src;
  });
}

/** 本地 File → Image */
export async function fileToImage(file) {
  const url = URL.createObjectURL(file);
  try {
    return await loadImg(url);
  } finally {
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }
}

/** 加载当前已部署的品牌 Logo 作为合成源 */
export async function fetchLogoImage() {
  return loadImg(ORIGIN + '/custom_brand/logo.png');
}

/** 拉取当前 logo.png 的原始字节，封装成 File（用于开关关闭时透传部署） */
export async function fetchPngFile(url) {
  const resp = await fetch(url || (ORIGIN + '/custom_brand/logo.png'));
  const buf = await resp.arrayBuffer();
  return new File([buf], 'logo_topbar.png', { type: 'image/png' });
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

/**
 * 检测左侧徽标区域：从最左开始，到第一个"透明空列"为止的连续不透明块。
 * 返回 {firstX, lastX, minY, maxY}（像素坐标）。
 * 若整图无空列（纯徽标无内嵌文字），则取最左 ~42% 宽作为徽标。
 */
function detectEmblem(img) {
  const W = img.naturalWidth;
  const H = img.naturalHeight;
  const c = document.createElement('canvas');
  c.width = W; c.height = H;
  const ctx = c.getContext('2d');
  ctx.drawImage(img, 0,0);
  const d = ctx.getImageData(0,0,W,H).data;
  const opaqueRatio = (x) => {
    let n = 0;
    for (let y = 0; y < H; y++) if (d[(y * W + x) * 4 + 3] > 30) n++;
    return n / H;
  };
  let started = false, firstX = W, lastX = 0, gapX = W;
  for (let x = 0; x < W; x++) {
    const r = opaqueRatio(x);
    if (r > 0.12) {
      if (!started) { started = true; firstX = x; }
      lastX = x;
    } else if (started) {
      gapX = x;
      break;
    }
  }
  if (gapX >= W) {
    // 无空列：取最左 42% 作为徽标，避免整图当徽标后文字溢出
    firstX = 0; lastX = Math.floor(W * 0.42);
  }
  let minY = H, maxY = 0;
  for (let x = firstX; x <= lastX; x++) {
    for (let y = 0; y < H; y++) {
      if (d[(y * W + x) * 4 + 3] > 30) { if (y < minY) minY = y; if (y > maxY) maxY = y; }
    }
  }
  if (maxY < minY) { minY = 0; maxY = H - 1; }
  return { firstX, lastX, minY, maxY };
}

/**
 * 生成蓝底适配成品：白色圆角卡片垫住左侧徽标 + 右侧白色粗体组织名。
 * @param {HTMLImageElement} img 源 Logo
 * @param {string} text 顶栏白色文字（组织名称）
 * @returns {Promise<Blob>} PNG Blob
 */
export function generateTopbarWhite(img, text) {
  const W = img.naturalWidth;
  const H = img.naturalHeight;
  const s = 2;                       // @2x，保证 HiDPI 清晰
  const H2 = H * s;
  const fs = Math.round(H2 * 0.40);   // 字号随图高自适应
  const pad = 5 * s;

  // 先量文字宽度，确定画布宽（文字可能比源图更宽）
  const measure = document.createElement('canvas').getContext('2d');
  measure.font = 'bold ' + fs + 'px "Microsoft YaHei","PingFang SC","Heiti SC",sans-serif';
  const textW = measure.measureText(text || '').width;

  const em = detectEmblem(img);
  const ew = (em.lastX - em.firstX + 1) * s;
  const eh = (em.maxY - em.minY + 1) * s;
  const chipW = ew + pad * 2;
  const chipH = eh + pad * 2;
  const cx = 2 * s;
  const cy = (H2 - chipH) / 2;
  const tx = cx + chipW + 10 * s;     // 白色文字起点
  const W2 = Math.max(W * s, Math.ceil(tx + textW + 8 * s));

  const out = document.createElement('canvas');
  out.width = W2; out.height = H2;
  const o = out.getContext('2d');
  o.fillStyle = '#ffffff';
  roundRect(o, cx, cy, chipW, chipH, 12 * s);
  o.fill();
  o.drawImage(img, em.firstX, em.minY, em.lastX - em.firstX + 1, em.maxY - em.minY + 1,
              cx + pad, cy + pad, ew, eh);
  o.fillStyle = '#ffffff';
  o.font = 'bold ' + fs + 'px "Microsoft YaHei","PingFang SC","Heiti SC",sans-serif';
  o.textBaseline = 'middle';
  o.fillText(text || '', tx, H2 / 2);
  return canvasToBlob(out);
}

/**
 * 开关关闭：把源 Logo 透传部署为 logo_topbar.png（白底卡片消失，恢复原始观感）。
 * @param {HTMLImageElement} img
 */
export function passthroughBlob(img) {
  const W = img.naturalWidth;
  const H = img.naturalHeight;
  const s = 2;
  const out = document.createElement('canvas');
  out.width = W * s; out.height = H * s;
  const o = out.getContext('2d');
  o.drawImage(img, 0, 0, W * s, H * s);
  return canvasToBlob(out);
}
