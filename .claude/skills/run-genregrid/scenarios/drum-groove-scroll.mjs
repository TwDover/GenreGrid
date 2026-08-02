export default async function (gg) {
  await gg.sleep(800);
  await gg.evaluate(`[...document.querySelectorAll('button')].find(b => b.title === 'Design a drum kit')?.click()`);
  await gg.sleep(400);
  await gg.evaluate(`document.querySelector('.dd-modal').scrollTo({ top: 900 })`);
  await gg.sleep(200);
  await gg.screenshot('/tmp/gg-groove-snare.png');
  await gg.evaluate(`document.querySelector('.dd-modal').scrollTo({ top: 2150 })`);
  await gg.sleep(200);
  await gg.screenshot('/tmp/gg-groove-audition.png');
}
