// Seekable motion for every scene. Positions are absolute seconds read from data-start,
// so the same markup always yields the same timeline. Calm and precise: short fades and slides, no bounce.
window.__timelines = window.__timelines || {};
const tl = gsap.timeline({ paused: true });
const TOTAL = __TOTAL__;
const scenes = Array.from(document.querySelectorAll('.scene'));
scenes.forEach((scene, i) => {
  const start = Number(scene.dataset.start);
  const end = scenes[i + 1] ? Number(scenes[i + 1].dataset.start) : TOTAL;
  // Cross-fade: the previous scene is still showing underneath for __FADE__ seconds.
  if (i) tl.fromTo(scene, { opacity: 0 }, { opacity: 1, duration: __FADE__, ease: 'power1.inOut' }, start);
  tl.fromTo(scene.querySelectorAll('.anim'), { opacity: 0, y: 22 }, { opacity: 1, y: 0, duration: 0.45, ease: 'power2.out', stagger: 0.14 }, start + 0.2);
  const image = scene.querySelector('.visual-image');
  if (image) tl.fromTo(image, { scale: 1 }, { scale: 1.04, duration: end - start, ease: 'none' }, start);
  tl.fromTo(scene.querySelector('.rule'), { scaleX: 0 }, { scaleX: 1, duration: end - start, ease: 'none' }, start);
});
tl.to({}, { duration: TOTAL }, 0);
window.__timelines.main = tl;
