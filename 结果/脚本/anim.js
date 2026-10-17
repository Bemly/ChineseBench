(function () {
  // 仅在 ?anim 时启用：静态导出保持最终画面
  if (!location.search.includes('anim')) return;
  const A = [];
  const ease = 'cubic-bezier(.2,.7,.2,1)';
  const add = (el, kf, delay, dur) => {
    const a = el.animate(kf, { delay, duration: dur, fill: 'both', easing: ease });
    a.pause();
    A.push(a);
  };
  const fadeUp = [{ opacity: 0, transform: 'translateY(28px)' }, { opacity: 1, transform: 'none' }];
  const pop = [{ opacity: 0, transform: 'scale(0)' }, { opacity: 1, transform: 'scale(1)' }];
  const card = document.querySelector('.card');
  [...card.children].forEach((el, i) => {
    const base = i < 2 ? i * 120 : 260 + (i - 2) * 380;
    add(el, fadeUp, base, 560);
    if (!el.classList.contains('panel')) return;
    el.querySelectorAll('table:not(.heat) tr').forEach((tr, j) =>
      add(tr, [{ opacity: 0, transform: 'translateX(-26px)' }, { opacity: 1, transform: 'none' }], base + 140 + j * 45, 440));
    el.querySelectorAll('.heat tr').forEach((tr, r) =>
      [...tr.children].forEach((td, c) =>
        add(td, [{ opacity: 0, transform: 'scale(.55)' }, { opacity: 1, transform: 'none' }], base + 120 + (r + c) * 26, 380)));
    el.querySelectorAll('.rd').forEach((d, j) => add(d, pop, base + 260 + j * 45, 420));
    el.querySelectorAll('.rl').forEach((ln, j) =>
      add(ln, [{ transform: 'scaleX(0)' }, { transform: 'scaleX(1)' }], base + 380 + j * 45, 650));
    el.querySelectorAll('.rlab').forEach((t, j) => add(t, [{ opacity: 0 }, { opacity: 1 }], base + 80 + j * 35, 380));
    el.querySelectorAll('.rp').forEach((p, j) => add(p, pop, base + 420 + j * 420, 950));
    el.querySelectorAll('.tile').forEach((t, j) =>
      add(t, [{ opacity: 0, transform: 'translateY(18px) scale(.95)' }, { opacity: 1, transform: 'none' }], base + 140 + j * 50, 440));
    el.querySelectorAll('.sp').forEach((p, j) =>
      add(p, [{ opacity: 0, transform: 'translateY(-16px)' }, { opacity: 1, transform: 'none' }], base + 180 + j * 11, 360));
  });
  const cnt = [...document.querySelectorAll('.cnt')].map(e => ({
    e, v: parseFloat(e.textContent), d: (e.textContent.split('.')[1] || '').length,
    t0: (() => { let p = e; while (p && !p.parentElement?.classList.contains('card')) p = p.parentElement; return p ? [...card.children].indexOf(p) : 2; })(),
  }));
  let end = 0;
  A.forEach(a => { const t = a.effect.getTiming(); end = Math.max(end, t.delay + t.duration); });
  window.__dur = end;
  window.__seek = ms => {
    A.forEach(a => (a.currentTime = ms));
    cnt.forEach(c => {
      const start = 260 + (c.t0 - 2) * 380 + 200;
      const p = Math.min(1, Math.max(0, (ms - start) / 1300));
      c.e.textContent = (c.v * (1 - Math.pow(1 - p, 3))).toFixed(c.d);
    });
  };
  window.__seek(0);
})();
