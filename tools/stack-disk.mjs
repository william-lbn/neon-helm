const quantityUnits = {
  '': 1, n: 1e-9, u: 1e-6, m: 1e-3, k: 1e3, M: 1e6, G: 1e9, T: 1e12, P: 1e15, E: 1e18,
  Ki: 2 ** 10, Mi: 2 ** 20, Gi: 2 ** 30, Ti: 2 ** 40, Pi: 2 ** 50, Ei: 2 ** 60,
};

function threshold(value, capacity) {
  if (value === undefined) return 0;
  const percent = typeof value === 'string' && /^\+?(?:\d+(?:\.\d*)?|\.\d+)%$/.test(value);
  if (percent) {
    const ratio = Number(value.slice(0, -1)) / 100;
    if (ratio < 1) return Math.ceil(capacity * ratio);
  } else if (typeof value === 'string') {
    const match = /^([+]?(?:\d+(?:\.\d*)?|\.\d+))([nukmMGTPE]|[KMGTPE]i|[eE][+-]?\d+)?$/.exec(value);
    if (match) {
      const [, base, unit = ''] = match;
      const rounded = Math.ceil(Object.hasOwn(quantityUnits, unit) ? Number(base) * quantityUnits[unit] : Number(base + unit));
      if (Number.isSafeInteger(rounded)) return rounded;
    }
  }
  throw new Error(`Invalid Kubelet disk eviction threshold ${value}`);
}

export function plannedDiskBytes(value = '0') {
  if (!/^\d+$/.test(value) || !Number.isSafeInteger(Number(value))) {
    throw new Error('--disk-working-set-bytes requires a nonnegative integer byte count');
  }
  return Number(value);
}

export function diskHeadroom(node, summary, config, workingSetBytes) {
  if (summary?.node?.nodeName !== node || !config || typeof config !== 'object' || Array.isArray(config)) {
    throw new Error(`Kubelet disk sample or configuration is unavailable on ${node}`);
  }
  const fields = [
    {name: 'nodefs', stats: summary.node.fs},
    {name: 'imagefs', stats: summary.node.runtime?.imageFs},
  ];

  function check(name, resource, capacity, available, planned) {
    const signal = `${name}.${resource}`;
    if (!Number.isSafeInteger(capacity) || capacity <= 0 || !Number.isSafeInteger(available) || available < 0 || available > capacity) {
      throw new Error(`Kubelet disk signal ${signal} is unavailable on ${node}`);
    }
    const hard = threshold(config.evictionHard?.[signal], capacity);
    const soft = threshold(config.evictionSoft?.[signal], capacity);
    const reclaim = Math.max(hard, soft) === 0 ? 0 : threshold(config.evictionMinimumReclaim?.[signal], capacity);
    const reserved = Math.max(hard, soft) + reclaim;
    return {signal, capacity, available, hard, soft, reclaim, planned, headroom: available - reserved - planned};
  }

  return fields.flatMap(({name, stats}) => {
    const available = check(name, 'available', stats?.capacityBytes, stats?.availableBytes, workingSetBytes);
    const result = [{...available, sampledAt: stats.time}];
    const inodeSignal = `${name}.inodesFree`;
    if (config.evictionHard?.[inodeSignal] !== undefined || config.evictionSoft?.[inodeSignal] !== undefined) {
      result.push({...check(name, 'inodesFree', stats.inodes, stats.inodesFree, 0), sampledAt: stats.time});
    }
    return result;
  });
}
