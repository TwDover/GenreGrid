// Verifies the Keyboard Shortcuts modal is fully reachable on a short window:
// shrink the viewport, open the modal, and confirm the last row (Quit) is
// scroll-reachable inside a capped, scrollable body rather than clipped off-screen.
export default async function (gg) {
  // Force a short renderer viewport so the ~19-row list would overflow.
  await gg.raw('Emulation.setDeviceMetricsOverride', {
    width: 1100, height: 620, deviceScaleFactor: 1, mobile: false,
  })
  await gg.sleep(200)

  await gg.evaluate(`[...document.querySelectorAll('button[title]')].find(b => /keyboard shortcuts/i.test(b.getAttribute('title')||''))?.click();`)
  await gg.sleep(400)
  await gg.screenshot('/tmp/gg-shortcuts-top.png')

  const info = await gg.evaluate(`
    const modal = document.querySelector('.shortcuts-modal');
    const body = document.querySelector('.shortcuts-body');
    const lastRow = [...document.querySelectorAll('.shortcut-desc')].pop();
    const modalRect = modal?.getBoundingClientRect();
    const before = {
      modalFitsViewport: modalRect ? modalRect.bottom <= window.innerHeight + 1 : null,
      bodyScrollable: body ? body.scrollHeight > body.clientHeight : null,
      bodyScrollHeight: body?.scrollHeight, bodyClientHeight: body?.clientHeight,
      lastRowText: lastRow?.textContent,
    };
    // Scroll to the bottom and check the last row is now within the body's box.
    if (body) body.scrollTop = body.scrollHeight;
    return before;
  `)
  await gg.sleep(300)
  await gg.screenshot('/tmp/gg-shortcuts-bottom.png')

  const after = await gg.evaluate(`
    const body = document.querySelector('.shortcuts-body');
    const lastRow = [...document.querySelectorAll('.shortcut-desc')].pop();
    const br = body.getBoundingClientRect(), lr = lastRow.getBoundingClientRect();
    return { lastRowVisibleAfterScroll: lr.bottom <= br.bottom + 2 && lr.top >= br.top - 2 };
  `)

  console.log('SHORTCUTS:', JSON.stringify({ ...info, ...after }))
}
