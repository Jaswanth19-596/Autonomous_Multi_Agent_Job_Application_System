"""Strict, verified Playwright program for one application dropdown."""

from __future__ import annotations

import json


def build_select_dropdown_option_code(field: str, option: str) -> str:
    """Build one browser program that opens a dropdown, then selects an option.

    ``field`` is a stable control id, name, automation id, aria-label, or
    visible label. The browser program deliberately resolves options only
    *after* clicking the control because custom dropdowns commonly render their
    menu in a portal on demand.
    """
    request = json.dumps({"field": field, "option": option}, ensure_ascii=False)
    return r"""
async (page) => {
  const request = REQUEST;
  const clean = value => String(value ?? '').trim().replace(/\s+/g, ' ');
  const norm = value => clean(value).toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
  const fieldKey = norm(request.field), wanted = norm(request.option);
  const steps = [];

  const usable = async locator => {
    try {
      return await locator.evaluate(el => {
        const style = getComputedStyle(el), rect = el.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden'
          && Number(style.opacity) !== 0 && rect.width > 0 && rect.height > 0
          && !el.disabled && el.getAttribute('aria-disabled') !== 'true'
          && !el.closest(
            '[aria-hidden="true"], [data-simplify-extension], [data-simplify-overlay], '
            + '[class*="simplify" i], [id*="simplify" i]'
          );
      });
    } catch (_) { return false; }
  };

  const labelOf = async locator => clean(await locator.evaluate(el => {
    const labelled = (el.getAttribute('aria-labelledby') || '').split(/\s+/)
      .map(id => document.getElementById(id)?.innerText).filter(Boolean).join(' ');
    const explicit = el.id
      ? document.querySelector(`label[for="${CSS.escape(el.id)}"]`)?.innerText
      : '';
    return el.getAttribute('aria-label') || labelled || explicit
      || (el.labels && Array.from(el.labels).map(label => label.innerText).join(' '))
      || el.closest('fieldset')?.querySelector('legend')?.innerText
      || el.closest(
        '.field, .form-group, [data-automation-id*="formField" i], '
        + '[class*="field" i], [role="group"]'
      )?.querySelector('label, legend, [data-automation-id*="label" i], [class*="label" i]')?.innerText
      || '';
  }));

  const controlSelector = [
    'select', 'button', 'input:not([type="hidden"])', '[role="combobox"]',
    '[aria-haspopup="listbox"]', '[aria-haspopup="menu"]',
    '[data-automation-id*="selectWidget" i]', '[data-automation-id*="dropdown" i]'
  ].join(', ');

  // Prefer an exact DOM identity. Snapshot targets sometimes point at a field
  // wrapper, so also accept its first usable descendant control.
  let control = null;
  const directSelectors = ['id', 'name', 'aria-label', 'data-automation-id'];
  for (const attribute of directSelectors) {
    const direct = page.locator(`[${attribute}=${JSON.stringify(request.field)}]`).first();
    if (!await direct.count() || !await direct.isVisible().catch(() => false)) continue;
    const isControl = await direct.evaluate(
      (element, selector) => element.matches(selector), controlSelector
    ).catch(() => false);
    if (isControl && await usable(direct)) {
      control = direct;
      break;
    }
    const child = direct.locator(controlSelector).first();
    if (await child.count() && await usable(child)) {
      control = child;
      break;
    }
  }

  if (!control) {
    const controls = page.locator(controlSelector);
    for (let index = 0; index < await controls.count(); index++) {
      const candidate = controls.nth(index);
      if (!await usable(candidate)) continue;
      const identities = [
        await candidate.getAttribute('id'),
        await candidate.getAttribute('name'),
        await candidate.getAttribute('aria-label'),
        await candidate.getAttribute('data-automation-id'),
        await labelOf(candidate),
      ];
      if (identities.some(identity => norm(identity) === fieldKey)) {
        control = candidate;
        break;
      }
    }
  }

  if (!control) {
    return JSON.stringify({
      status: 'unresolved', failure_code: 'control_not_found',
      field: request.field, requested_option: request.option,
      phase: 'locate_control', interaction_steps: steps, retryable: true,
    });
  }

  const fieldLabel = await labelOf(control)
    || clean(await control.getAttribute('id'))
    || clean(await control.getAttribute('name'))
    || request.field;
  const tag = await control.evaluate(el => el.tagName.toLowerCase());

  // Native selects keep their options in the DOM, but still open the control
  // first so every dropdown follows the same observable interaction order.
  if (tag === 'select') {
    await control.click({timeout: 5000});
    steps.push('clicked_control');
    const options = await control.locator('option').evaluateAll(nodes => nodes.map(node => ({
      label: (node.textContent || '').trim().replace(/\s+/g, ' '),
      value: node.value,
      disabled: node.disabled,
    })).filter(candidate => candidate.label && !candidate.disabled));
    steps.push('options_rendered');
    const exact = options.find(candidate =>
      norm(candidate.label) === wanted || norm(candidate.value) === wanted
    );
    if (!exact) {
      await page.keyboard.press('Escape').catch(() => {});
      return JSON.stringify({
        status: 'unresolved', failure_code: 'option_not_found', field: fieldLabel,
        requested_option: request.option,
        available_options: options.map(candidate => candidate.label),
        phase: 'select_option', interaction_steps: steps, retryable: false,
      });
    }
    await control.selectOption({value: exact.value}, {timeout: 5000});
    steps.push('selected_option');
    const selected = await control.locator('option:checked').evaluate(node => ({
      label: node.textContent || '', value: node.value,
    }));
    if (norm(selected.label) !== norm(exact.label) && norm(selected.value) !== norm(exact.value)) {
      return JSON.stringify({
        status: 'unresolved', failure_code: 'option_not_committed', field: fieldLabel,
        requested_option: request.option, selected_option: clean(selected.label),
        phase: 'verify_selection', interaction_steps: steps, retryable: true,
      });
    }
    return JSON.stringify({
      status: 'selected', field: fieldLabel, selected_option: exact.label,
      interaction_steps: steps,
    });
  }

  const optionSelector = [
    '[role="option"]', '[role="menuitem"]', '[role="radio"]',
    '[data-automation-id="promptOption"]', '[data-automation-id="menuItem"]',
    '[data-automation-id*="option" i]', '[id*="-option-"]', 'li'
  ].join(', ');
  const popupSelector = [
    '[role="listbox"]:visible', '[role="menu"]:visible',
    '[data-automation-id*="menu" i]:visible',
    '[data-automation-id*="popup" i]:visible',
    '[class*="listbox" i]:visible', '[class*="dropdown-menu" i]:visible'
  ].join(', ');
  const visibilityMarker = `agent-dropdown-${Date.now()}-${Math.random()}`;

  // Mark only options that were already visible. Options that existed but were
  // hidden are intentionally treated as newly exposed after the click.
  await page.locator(optionSelector).evaluateAll((nodes, marker) => {
    for (const node of nodes) {
      const style = getComputedStyle(node), rect = node.getBoundingClientRect();
      if (style.display !== 'none' && style.visibility !== 'hidden'
          && Number(style.opacity) !== 0 && rect.width > 0 && rect.height > 0) {
        node.setAttribute('data-agent-dropdown-preexisting', marker);
      }
    }
  }, visibilityMarker).catch(() => {});

  const cleanup = async payload => {
    await page.locator(`[data-agent-dropdown-preexisting=${JSON.stringify(visibilityMarker)}]`)
      .evaluateAll(nodes => nodes.forEach(node => node.removeAttribute('data-agent-dropdown-preexisting')))
      .catch(() => {});
    return JSON.stringify(payload);
  };

  const stateOf = async () => clean(await control.evaluate(el => {
    const root = el.closest(
      'fieldset, [role="group"], [data-automation-id*="formField" i], '
      + '.field, .form-group, [class*="field" i]'
    ) || el.parentElement;
    const selected = root?.querySelector(
      '[aria-selected="true"], [aria-checked="true"], option:checked, '
      + '[data-automation-id*="selected" i], [class*="selected-value" i], [class*="singleValue" i]'
    );
    return [
      el.getAttribute('aria-valuetext'),
      el.tagName === 'BUTTON' ? (el.innerText || el.textContent) : el.value,
      selected?.getAttribute('aria-label'), selected?.innerText,
      selected?.textContent, selected?.value,
    ].filter(Boolean).join(' | ');
  }));

  const beforeState = await stateOf();
  await control.scrollIntoViewIfNeeded().catch(() => {});
  await control.click({timeout: 5000});
  steps.push('clicked_control');

  const collectOptions = async () => {
    const found = [], seen = new Set();
    const append = async (candidate, allowPreexisting) => {
      if (!await candidate.isVisible().catch(() => false)) return;
      if (!allowPreexisting
          && await candidate.getAttribute('data-agent-dropdown-preexisting') === visibilityMarker) return;
      const data = await candidate.evaluate(node => ({
        label: (node.getAttribute('aria-label') || node.innerText || node.textContent || '')
          .trim().replace(/\s+/g, ' '),
        disabled: node.getAttribute('aria-disabled') === 'true' || node.hasAttribute('disabled'),
      })).catch(() => ({label: '', disabled: true}));
      if (!data.label || data.disabled) return;
      const box = await candidate.boundingBox().catch(() => null);
      const key = `${data.label}|${Math.round(box?.x || 0)}|${Math.round(box?.y || 0)}`;
      if (seen.has(key)) return;
      seen.add(key);
      found.push({locator: candidate, label: data.label});
    };

    const ownedIds = clean(
      (await control.getAttribute('aria-controls')) || (await control.getAttribute('aria-owns'))
    ).split(/\s+/).filter(Boolean);
    const roots = [];
    for (const id of ownedIds) {
      const root = page.locator(`[id=${JSON.stringify(id)}]`).first();
      if (await root.count() && await root.isVisible().catch(() => false)) {
        roots.push({locator: root, allowPreexisting: true});
      }
    }
    const popups = page.locator(popupSelector);
    for (let index = (await popups.count()) - 1; index >= 0; index--) {
      const root = popups.nth(index);
      if (await root.isVisible().catch(() => false)) {
        roots.push({locator: root, allowPreexisting: false});
      }
    }

    for (const entry of roots) {
      const root = entry.locator;
      const candidates = root.locator(optionSelector);
      for (let index = 0; index < await candidates.count(); index++) {
        await append(candidates.nth(index), entry.allowPreexisting);
      }
      // Some portals omit option roles but still expose an exact text node.
      if (!found.some(candidate => norm(candidate.label) === wanted)) {
        const exactText = root.getByText(request.option, {exact: true});
        for (let index = 0; index < await exactText.count(); index++) {
          await append(exactText.nth(index), entry.allowPreexisting);
        }
      }
    }

    if (!found.length) {
      const candidates = page.locator(optionSelector);
      for (let index = 0; index < await candidates.count(); index++) {
        await append(candidates.nth(index), false);
      }
    }
    return found;
  };

  const waitForOptions = async () => {
    for (let attempt = 0; attempt < 40; attempt++) {
      const options = await collectOptions();
      if (options.length) return options;
      await page.waitForTimeout(100);
    }
    return [];
  };

  let options = await waitForOptions();
  steps.push('options_rendered');
  let exact = options.find(candidate => norm(candidate.label) === wanted);

  // Searchable comboboxes may render the desired option only after text is
  // entered. Crucially, typing happens after the control has been opened.
  if (!exact && await control.isEditable().catch(() => false)) {
    await control.fill('', {timeout: 5000});
    await control.fill(String(request.option), {timeout: 5000});
    steps.push('filtered_options');
    options = await waitForOptions();
    exact = options.find(candidate => norm(candidate.label) === wanted);
  }

  if (!options.length) {
    await page.keyboard.press('Escape').catch(() => {});
    return await cleanup({
      status: 'unresolved', failure_code: 'options_unavailable', field: fieldLabel,
      requested_option: request.option, available_options: [],
      phase: 'wait_for_options', interaction_steps: steps, retryable: true,
    });
  }
  if (!exact) {
    await page.keyboard.press('Escape').catch(() => {});
    return await cleanup({
      status: 'unresolved', failure_code: 'option_not_found', field: fieldLabel,
      requested_option: request.option,
      available_options: [...new Set(options.map(candidate => candidate.label))],
      phase: 'select_option', interaction_steps: steps, retryable: false,
    });
  }

  await exact.locator.scrollIntoViewIfNeeded().catch(() => {});
  await exact.locator.click({timeout: 5000});
  steps.push('selected_option');
  await page.waitForTimeout(250);

  const afterState = await stateOf();
  const optionSelected = await exact.locator.evaluate(node =>
    node.getAttribute('aria-selected') === 'true'
      || node.getAttribute('aria-checked') === 'true'
      || (node.matches('input[type="radio"], input[type="checkbox"]') && node.checked)
  ).catch(() => false);
  const optionClosed = !await exact.locator.isVisible().catch(() => false);
  const stateMatches = norm(afterState) === wanted || norm(afterState).includes(wanted);
  const stateChanged = norm(afterState) !== norm(beforeState);
  if (!optionSelected && !optionClosed && !stateMatches && !stateChanged) {
    return await cleanup({
      status: 'unresolved', failure_code: 'option_not_committed', field: fieldLabel,
      requested_option: request.option, selected_option: afterState || null,
      phase: 'verify_selection', interaction_steps: steps, retryable: true,
    });
  }

  return await cleanup({
    status: 'selected', field: fieldLabel, selected_option: exact.label,
    interaction_steps: steps,
  });
}
""".replace("REQUEST", request)
