// 共用：設定、格式化、底部分頁
const LINKS = {
  yahoo: id => `https://tw.stock.yahoo.com/quote/${id}.TW`,     // 盤中走勢（即時、不會睡著）
  wantgoo: id => `https://www.wantgoo.com/stock/${id}`,
  warroom: '',   // 新的個股戰情室網址（Streamlit），做好後填上，例如 'https://xxx.streamlit.app'
};

const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = (x, d = 1) => x == null ? '—' : Number(x).toLocaleString('zh-TW', {minimumFractionDigits: d, maximumFractionDigits: d});
const fmtPrice = x => x == null ? '—' : (x >= 1000 ? fmt(x, 0) : fmt(x, x >= 100 ? 1 : 2));
const sign = x => x == null ? '' : (x > 0 ? '+' : x < 0 ? '−' : '±');
const pctText = (x, d = 1) => x == null ? '—' : `${sign(x)}${Math.abs(x).toFixed(d)}%`;
const cls = x => x == null ? 'flat' : x > 0 ? 'up' : x < 0 ? 'down' : 'flat';
const md = s => { const [, m, d] = s.split('-'); return `${+m}/${+d}`; };
const WEEK = '日一二三四五六';
const mdw = s => `${md(s)}（${WEEK[new Date(s + 'T00:00:00+08:00').getDay()]}）`;

async function getJSON(url) {
  const r = await fetch(url, {cache: 'no-cache'});
  if (!r.ok) throw new Error(`${url}：${r.status}`);
  return r.json();
}

function renderNav(current) {
  const items = [
    ['index', '📋', '今日', 'index.html'],
    ['score', '📈', '成績單', null],
    ['light', '🚦', '大盤燈號', null],
    ['me', '📝', '我的紀錄', null],
  ];
  const nav = document.createElement('nav');
  nav.className = 'tabs';
  nav.setAttribute('aria-label', '頁面');
  nav.innerHTML = '<ul>' + items.map(([k, i, t, href]) =>
    href ? `<li><a href="${href}"${k === current ? ' aria-current="page"' : ''}><span class="i">${i}</span>${t}</a></li>`
         : `<li><a class="soon" aria-disabled="true" title="製作中"><span class="i">${i}</span>${t}</a></li>`).join('') + '</ul>';
  document.body.appendChild(nav);
}
