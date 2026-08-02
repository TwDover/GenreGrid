export default async function (gg) {
  await gg.sleep(800);
  await gg.evaluate(`
    const btn = [...document.querySelectorAll('button')].find(b => b.title === 'Design a drum kit');
    btn.click();
  `);
  await gg.sleep(500);
  await gg.evaluate(`document.querySelector('.dd-modal').scrollTo({ top: 1400 })`);
  await gg.sleep(200);
  await gg.screenshot('/tmp/gg-drum-designer-mid.png');
  await gg.evaluate(`document.querySelector('.dd-modal').scrollTo({ top: 100000 })`);
  await gg.sleep(200);
  await gg.screenshot('/tmp/gg-drum-designer-bottom.png');
}
