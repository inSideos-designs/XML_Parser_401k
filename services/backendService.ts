export type BackendResult = {
  fileNames: string[];
  rows: { promptText: string; values: { [fileName: string]: string } }[];
};

export async function processViaBackend(opts: {
  endpoint?: string;
  mapFile?: File | null;
  datapointsFile?: File | null;
  xmlFiles: File[];
}): Promise<BackendResult> {
  const defaultBase = 'http://localhost:8787';
  const base = (opts.endpoint || defaultBase).replace(/\/$/, '');
  // If no map/datapoints provided, prefer the JSON endpoint using server defaults
  if (!opts.mapFile && !opts.datapointsFile) {
    const xmlFilesPayload = await Promise.all(opts.xmlFiles.map(async (f) => ({
      name: f.name,
      content: await f.text(),
    })));
    const resp = await fetch(`${base}/process-json`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ xmlFiles: xmlFilesPayload }),
    });
    if (!resp.ok) {
      const text = await resp.text().catch(() => '');
      throw new Error(`Backend error ${resp.status}: ${text}`);
    }
    return resp.json();
  } else {
    const fd = new FormData();
    if (opts.mapFile) fd.append('map_file', opts.mapFile);
    if (opts.datapointsFile) fd.append('datapoints_file', opts.datapointsFile);
    for (const xf of opts.xmlFiles) fd.append('xml_files', xf);
    const resp = await fetch(`${base}/process`, { method: 'POST', body: fd });
    if (!resp.ok) {
      const text = await resp.text().catch(() => '');
      throw new Error(`Backend error ${resp.status}: ${text}`);
    }
    return resp.json();
  }
}
