/*
 * Example scenario for `node driver.mjs run scenarios/open-setup.mjs`.
 *
 * Drives the real UI with no source changes: from the empty state, click the
 * "Open Setup" button, wait for the Setup drawer, and screenshot it. Shows the
 * scenario shape — clicks go through evaluate() (querySelector + .click()), not a
 * coordinate system.
 *
 * `gg` = { evaluate, screenshot, waitReady, raw(method,params), sleep }.
 */
export default async function (gg) {
  // Click the button whose text is "Open Setup" (empty-state CTA) or the header "Setup".
  const clicked = await gg.evaluate(`
    const byText = (t) => [...document.querySelectorAll('button')].find(b => b.textContent.trim().includes(t));
    const b = byText('Open Setup') || byText('Setup');
    if (b) { b.click(); return b.textContent.trim(); }
    return null;
  `);
  if (!clicked) throw new Error('could not find a Setup button');
  await gg.sleep(600);

  const state = await gg.evaluate(`
    const drawerOpen = !!document.querySelector('[class*=drawer], [class*=setup], form');
    const hasStyleSelect = !!document.querySelector('select');
    const generateBtn = [...document.querySelectorAll('button')].some(b => /generate|create|build/i.test(b.textContent));
    return { clicked: ${JSON.stringify(clicked)}, drawerOpen, hasStyleSelect, generateBtn };
  `);
  const out = (process.env.GG_SHOT || '/tmp/gg-setup.png');
  await gg.screenshot(out);
  console.log('SCENARIO', JSON.stringify(state));
  console.log('SCREENSHOT', out);
}
