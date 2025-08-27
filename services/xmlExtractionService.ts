import type { Prompt, OptionsByPrompt } from '../types';

type LinkFlag = {
  selected: number;
  insert: number;
  text?: string;
};

function parseXmlToFlags(xml: string): Record<string, LinkFlag> {
  const flags: Record<string, LinkFlag> = {};
  const parser = new DOMParser();
  const doc = parser.parseFromString(xml, 'application/xml');

  // Handle <LinkName value="..." selected="0/1" insert="0/1">text?</LinkName>
  const linkNodes = Array.from(doc.getElementsByTagName('LinkName'));
  for (const el of linkNodes) {
    const name = (el.getAttribute('value') || '').trim();
    if (!name) continue;
    const selected = parseInt(el.getAttribute('selected') || '0', 10) || 0;
    const insert = parseInt(el.getAttribute('insert') || '0', 10) || 0;
    const text = (el.textContent || '').trim() || undefined;
    flags[name] = { selected, insert, text };
  }

  // Handle <PlanData FieldName="...">text?</PlanData> (presence => selected)
  const planDataNodes = Array.from(doc.getElementsByTagName('PlanData'));
  for (const el of planDataNodes) {
    const name = (el.getAttribute('FieldName') || '').trim();
    if (!name) continue;
    const text = (el.textContent || '').trim() || undefined;
    // Only set if not present; prefer LinkName version when both exist
    if (!flags[name]) {
      flags[name] = { selected: 1, insert: 0, text };
    } else if (text && !flags[name].text) {
      flags[name].text = text;
    }
  }
  return flags;
}

function looksYesNoPrompt(promptText: string): boolean {
  const p = (promptText || '').trim().toLowerCase();
  return /\?$/.test(p) && /^(is|does|will|are|has|have)\b/.test(p);
}

function relatedText(name: string, flags: Record<string, LinkFlag>): string | undefined {
  const lf = flags[name];
  if (lf && lf.text && lf.text.trim()) return lf.text;
  if (name.endsWith('Main')) {
    const base = name.slice(0, -4);
    const lf2 = flags[base];
    if (lf2 && lf2.text && lf2.text.trim()) return lf2.text;
  }
  const suffixes = ['Age','Amt','Amount','Perc','Percent','Dollar','Dollars'];
  for (const suf of suffixes) {
    const lf3 = flags[`${name}${suf}`];
    if (lf3 && lf3.text && lf3.text.trim()) return lf3.text;
  }
  return undefined;
}

function cleanName(n: string): string {
  return n.replace(/^"|"$/g, '').trim();
}

function chooseValueForLinkcsv(linkcsv: string, promptText: string, flags: Record<string, LinkFlag>): string | null {
  const names = (linkcsv || '')
    .split(',')
    .map(s => cleanName(s))
    .filter(Boolean);
  if (names.length === 0) return null;

  // Single-name fast path
  if (names.length === 1) {
    const nm = names[0];
    const lf = flags[nm];
    if (!lf) return null;
    if (looksYesNoPrompt(promptText)) {
      return lf.selected === 1 ? 'Yes' : 'No';
    }
    const txt = relatedText(nm, flags);
    if (txt) return txt;
    if (/^yes/i.test(nm)) return lf.selected === 1 ? 'Yes' : 'No';
    if (/^no/i.test(nm)) return lf.selected === 1 ? 'No' : 'Yes';
    return null;
  }

  // Multi-name: pick the selected one
  let chosen: string | null = null;
  for (const nm of names) {
    const lf = flags[nm];
    if (lf && lf.selected === 1) { chosen = nm; break; }
  }
  if (!chosen) return null;
  if (looksYesNoPrompt(promptText)) {
    if (/yes/i.test(chosen)) return 'Yes';
    if (/no/i.test(chosen)) return 'No';
    return 'Yes'; // default when selected for Y/N style
  }
  const txt = relatedText(chosen, flags);
  if (txt) return txt;
  // As a last resort, prefer not to leak internal linkname; mark unknown
  return null;
}

function deriveLabelFromQuick(quick?: string): string | null {
  if (!quick) return null;
  const q = quick.trim();
  if (!q) return null;
  if (q.includes(',')) {
    const label = q.split(',').pop()!.trim().replace(/^"|"$/g, '');
    return label || null;
  }
  return null;
}

export async function fillDataFromXmls(
  prompts: Prompt[],
  xmlFiles: { name: string; content: string }[],
  onProgress: (progress: number) => void
): Promise<{ [fileName: string]: { [key: string]: string } }> {
  const results: { [fileName: string]: { [key: string]: string } } = {};
  let processed = 0;
  for (const file of xmlFiles) {
    try {
      const flags = parseXmlToFlags(file.content);
      const row: { [key: string]: string } = {};
      for (const p of prompts) {
        const key = (p.key || '').trim();
        const linkcsv = (p.linknames || p.key || '').trim();
        if (!key) { continue; }
        let val = chooseValueForLinkcsv(linkcsv, p.prompt || '', flags);
        if (val == null && p.quick) {
          // If one of the mapped linknames is selected, try to derive a user-facing label from quick text
          const names = (linkcsv || '').split(',').map(s => cleanName(s)).filter(Boolean);
          let anySelected = names.some(n => flags[n] && flags[n].selected === 1);
          // If none of the mapped names are selected, fall back to any selected flag
          if (!anySelected) {
            anySelected = Object.values(flags).some(f => f && f.selected === 1);
          }
          if (anySelected) {
            const label = deriveLabelFromQuick(p.quick);
            if (label) val = label;
          }
        }
        row[p.key] = val ?? 'N/A';
      }
      results[file.name] = row;
    } catch (e) {
      const row: { [key: string]: string } = {};
      for (const p of prompts) row[p.key] = 'Processing Error';
      results[file.name] = row;
      // eslint-disable-next-line no-console
      console.error('Failed processing XML', file.name, e);
    } finally {
      processed += 1;
      onProgress(processed / xmlFiles.length);
    }
  }
  return results;
}

function linknameKeywords(name: string): Set<string> {
  const kws = new Set<string>();
  const n = name.toLowerCase();
  if (n.includes('match')) kws.add('match');
  if (n.includes('profit') || n.includes('non elective') || n.includes('nonelective')) kws.add('profit');
  if (n.includes('immediate') || n.includes('vest100')) kws.add('immediate');
  if (n.includes('percent') || n.includes('perc')) kws.add('percent');
  if (n.includes('dollar')) kws.add('dollar');
  const nums = n.match(/\d+/g) || [];
  nums.forEach(x => kws.add(x));
  return kws;
}

function normalizeOptionsAllowed(txt: string): string[] {
  const t = (txt || '').replace(/\\n/g, '\n');
  return t.split(/\n+/).map(s => s.trim()).filter(Boolean);
}

function bestMatchFromOptions(selectedNames: string[], optionsAllowed: string): string | null {
  if (!selectedNames.length || !optionsAllowed) return null;
  const selKw = new Set<string>();
  selectedNames.forEach(n => linknameKeywords(n).forEach(k => selKw.add(k)));
  const options = normalizeOptionsAllowed(optionsAllowed);
  let best: string | null = null; let bestScore = 0;
  for (const opt of options) {
    const low = opt.toLowerCase();
    let score = 0;
    selKw.forEach(k => { if (low.includes(k)) score++; });
    if (score > bestScore) { best = opt; bestScore = score; }
  }
  return best;
}

function isVestingSchedulePrompt(promptText: string): boolean {
  const p = (promptText || '').trim().toLowerCase();
  return p.includes('vesting schedule') && !p.includes('describe');
}

function deriveVestingShortLabel(flags: Record<string, LinkFlag>, quickText?: string): string | null {
  // Graded schedules
  const gradedMap: Record<string, string> = {
    'Vest6YRGradeMatch': '2-20',
    'Vest5YRGradeMatch': '1-20',
    'Vest4YRGradeMatch': '1-25',
    '6YRGradedNEContr': '2-20',
    '5YRGradedNEContr': '1-20',
    '4YRGradedNEContr': '1-25',
  };
  for (const [nm, label] of Object.entries(gradedMap)) {
    const lf = flags[nm];
    if (lf && lf.selected === 1) return label;
  }
  // Cliff schedules
  const cliffMap: Record<string, string> = {
    'Vest3YRClifMatch': 'Cliff 3',
    '3YRCliffNEContr': 'Cliff 3',
    '2YRCliffNEContr': 'Cliff 2',
  };
  for (const [nm, label] of Object.entries(cliffMap)) {
    const lf = flags[nm];
    if (lf && lf.selected === 1) return label;
  }
  // Immediate across money types
  const qt = (quickText || '').toLowerCase();
  const isMatch = qt.includes('match');
  const isNE = qt.includes('non elective') || qt.includes('non-elective') || qt.includes('profit');
  if (isMatch) {
    for (const nm of ['NAVestMatch', 'Vest100Match']) {
      const lf = flags[nm];
      if (lf && lf.selected === 1) return 'Immediate';
    }
  }
  if (isNE) {
    for (const nm of ['100VestingNEContr', 'Vest100NEContr']) {
      const lf = flags[nm];
      if (lf && lf.selected === 1) return 'Immediate';
    }
  }
  for (const nm of ['VestNAQACA', 'VestNAQACAMatch', 'VestNAQACANE']) {
    const lf = flags[nm];
    if (lf && lf.selected === 1) return 'Immediate';
  }
  return null;
}

function expandVestingLabel(shortLabel: string, optionsAllowed: string): string | null {
  if (!shortLabel) return null;
  const txt = (optionsAllowed || '').replace(/\\n/g,'\n');
  const lines = txt.split(/\n+/).map(s => s.trim()).filter(Boolean);
  const s = shortLabel.trim().toLowerCase().replace(/\s+/g,'');
  const candidates = new Set<string>([s]);
  if (s === 'cliff2' || s === 'cliff3') candidates.add(s.replace('cliff','cliff '));
  if (s === '1-20') candidates.add('20/yr');
  for (const line of lines) {
    const low = line.toLowerCase().replace(/\s+/g,'');
    for (const c of candidates) {
      if (low.startsWith(c)) return line;
    }
  }
  // Canonical verbose forms
  switch (s) {
    case '1-25': return '1-25 (0=0, 1=25, 2=50, 3=75, 4=100)';
    case '1-20': return '20/Yr (0=0, 1=20, 2=40, 3=60, 4=80, 5=100)';
    case '2-20': return '2-20 (0=0, 1=0, 2=20, 3=40, 4=60, 5=80, 6=100)';
    case 'cliff2': case 'cliff 2': return 'Cliff 2 (0=0, 1=0, 2=100)';
    case 'cliff3': case 'cliff 3': return 'Cliff 3 (0=0, 1=0, 2=0, 3=100)';
    case 'immediate': return 'Immediate (100% immediate vesting)';
  }
  return shortLabel;
}

export async function fillDataFromXmlsEnhanced(
  prompts: Prompt[],
  xmlFiles: { name: string; content: string }[],
  optionsByPrompt: OptionsByPrompt,
  onProgress: (progress: number) => void
): Promise<{ [fileName: string]: { [key: string]: string } }> {
  const results: { [fileName: string]: { [key: string]: string } } = {};
  let processed = 0;
  for (const file of xmlFiles) {
    try {
      const flags = parseXmlToFlags(file.content);
      const row: { [key: string]: string } = {};
      // Helper to normalize prompt like Python normalize_text
      const norm = (s: string) => (s || '').trim().replace(/\s+/g,' ').replace(/:$/,'');
      for (const p of prompts) {
        const key = (p.key || '').trim();
        const linkcsv = (p.linknames || p.key || '').trim();
        if (!key) continue;
        let val = chooseValueForLinkcsv(linkcsv, p.prompt || '', flags);
        // Vesting schedule special-case mapping
        if (val == null && isVestingSchedulePrompt(p.prompt || '')) {
          const short = deriveVestingShortLabel(flags, p.quick);
          if (short) {
            const oa = optionsByPrompt[p.prompt || ''] || '';
            const expanded = expandVestingLabel(short, oa);
            if (expanded) val = expanded;
          }
        }
        if (val == null) {
          const names = (linkcsv || '').split(',').map(s => cleanName(s)).filter(Boolean);
          let selected = names.filter(n => flags[n] && flags[n].selected === 1);
          const allSelected = Object.entries(flags).filter(([,f]) => f && f.selected === 1).map(([n]) => n);
          const oa = optionsByPrompt[p.prompt] || optionsByPrompt[norm(p.prompt || '')] || '';
          let picked = bestMatchFromOptions(selected, oa);
          // If none of the mapped names are selected, try using all selected flags for matching
          if (!picked && selected.length === 0) {
            picked = bestMatchFromOptions(allSelected, oa);
          }
          if (picked) val = picked;
          // Still nothing? Try label from quick text when any mapped name is selected
          if (val == null && (selected.length > 0 || allSelected.length > 0)) {
            const label = deriveLabelFromQuick(p.quick);
            if (label) val = label;
          }
        }
        row[p.key] = val ?? 'N/A';
      }
      results[file.name] = row;
    } catch (e) {
      const row: { [key: string]: string } = {};
      for (const p of prompts) row[p.key] = 'Processing Error';
      results[file.name] = row;
      console.error('Failed processing XML', file.name, e);
    } finally {
      processed += 1;
      onProgress(processed / xmlFiles.length);
    }
  }
  return results;
}
