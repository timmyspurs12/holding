/**
 * GenLayer networks, in the shape a browser wallet wants them (EIP-3085).
 *
 * Chain ids match services/lib/genlayer/config.py::DEFAULT_CHAIN_ID. Chain id
 * 0 is not a network: it means the Reporter is in DEMO mode, where there is no
 * chain to connect to and nothing to switch.
 */

export interface ChainSpec {
  id: number;
  hex: string;
  name: string;
  rpc: string;
  symbol: string;
  explorer: string;
}

export const GENLAYER_CHAINS: Record<number, ChainSpec> = {
  4221: {
    id: 4221,
    hex: "0x107d",
    name: "GenLayer Bradbury",
    rpc: "https://rpc-bradbury.genlayer.com",
    symbol: "GEN",
    explorer: "https://explorer-bradbury.genlayer.com",
  },
  61999: {
    id: 61999,
    hex: "0xf22f",
    name: "GenLayer Asimov",
    rpc: "https://rpc-asimov.genlayer.com",
    symbol: "GEN",
    explorer: "https://explorer-asimov.genlayer.com",
  },
  61127: {
    id: 61127,
    hex: "0xeec7",
    name: "GenLayer Localnet",
    rpc: "http://127.0.0.1:4000/api",
    symbol: "GEN",
    explorer: "",
  },
};

export function chainSpec(id: number): ChainSpec | null {
  return GENLAYER_CHAINS[id] ?? null;
}

export function chainName(id: number): string {
  return chainSpec(id)?.name ?? `Chain ${id}`;
}

export function shortAddress(address: string): string {
  if (!address || address.length < 12) return address || "";
  return `${address.slice(0, 6)}…${address.slice(-4)}`;
}
