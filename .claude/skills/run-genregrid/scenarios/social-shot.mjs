// Captures a dark-theme piano-roll frame for the GitHub social-preview card:
// generate a loop, switch to dark theme, expand, scroll to the per-part rolls.
export default async function (gg) {
  await gg.evaluate(`[...document.querySelectorAll('button')].find(b => /open setup/i.test(b.textContent))?.click();`)
  await gg.sleep(700)
  await gg.evaluate(`
    const gen = [...document.querySelectorAll('button')].find(b => b.type === 'submit' && /generate/i.test(b.textContent));
    gen?.click();
  `)
  await gg.sleep(4500)

  // Switch to dark theme (README shots are dark; notes pop more).
  await gg.evaluate(`
    for (let i = 0; i < 4 && document.documentElement.dataset.theme !== 'dark'; i++) {
      [...document.querySelectorAll('button[title]')].find(b => /^theme:/i.test(b.getAttribute('title')||''))?.click();
    }
  `)
  await gg.sleep(400)

  await gg.evaluate(`if (!document.querySelector('.history-entry.expanded')) document.querySelector('.history-row')?.click();`)
  await gg.sleep(900)

  // Scroll so the per-part rolls (with names) sit under the header.
  await gg.evaluate(`document.querySelector('.part-cards')?.scrollIntoView({ block: 'start' });`)
  await gg.sleep(400)
  await gg.screenshot('/tmp/social-dark-rolls.png')

  const state = await gg.evaluate(`return { theme: document.documentElement.dataset.theme, expanded: !!document.querySelector('.history-entry.expanded') };`)
  console.log('SOCIAL-SHOT:', JSON.stringify(state))
}
