#!/usr/bin/env node
// On-chain pick attestation: anchors the SHA-256 of a ledger entry in a Solana
// memo transaction, making the prediction impossible to backdate. Verification
// needs no trust in us: recompute the hash from the ledger entry and compare it
// with the memo recorded on-chain.
//
// Usage:
//   node attest.mjs attest <ledger.json> <pickId>            # sends the memo tx
//   node attest.mjs verify <ledger.json> <pickId> <txSig>    # recompute + compare
//
// Env:
//   ATTEST_KEYPAIR  path to a Solana keypair JSON (attest only)
//   SOLANA_RPC      RPC endpoint (default: mainnet-beta public RPC)
//
// The hash is computed over the canonical form of the ledger entry: JSON with
// keys sorted lexicographically at every level and no whitespace. The memo is
// the string  voight-pick:<sha256-hex>.

import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import bs58 from "bs58";
import {
  Connection,
  Keypair,
  PublicKey,
  Transaction,
  TransactionInstruction,
  sendAndConfirmTransaction,
} from "@solana/web3.js";

const MEMO_PROGRAM = new PublicKey("Memo1UhkJRfHyvLMcVucJwxXeuD728EqVDDwQDxFMNo");
const RPC = process.env.SOLANA_RPC ?? "https://api.mainnet-beta.solana.com";
const PREFIX = process.env.MEMO_PREFIX ?? "voight-pick";

function canonical(value) {
  if (Array.isArray(value)) return "[" + value.map(canonical).join(",") + "]";
  if (value && typeof value === "object") {
    return (
      "{" +
      Object.keys(value)
        .sort()
        .map((k) => JSON.stringify(k) + ":" + canonical(value[k]))
        .join(",") +
      "}"
    );
  }
  return JSON.stringify(value);
}

// The attestation covers the immutable PREDICTION CORE — what was predicted and
// when — not mutable settlement fields (status/odds/settled change after the
// event and must not invalidate the anchor). Both the on-chain writer and this
// verifier hash exactly this projection.
function core(entry) {
  const c = { id: entry.id, date: entry.date, market: entry.market, pick: entry.pick };
  if (typeof entry.prob === "number") c.prob = entry.prob;
  return c;
}

function pickEntry(ledgerPath, pickId) {
  const ledger = JSON.parse(readFileSync(ledgerPath, "utf8"));
  const entry = ledger.find((e) => String(e.id) === String(pickId));
  if (!entry) throw new Error(`pick id ${pickId} not found in ${ledgerPath}`);
  return entry;
}

const hashOf = (entry) => createHash("sha256").update(canonical(core(entry))).digest("hex");

async function attest(ledgerPath, pickId) {
  const keypairPath = process.env.ATTEST_KEYPAIR;
  if (!keypairPath) throw new Error("ATTEST_KEYPAIR is not set");
  const payer = Keypair.fromSecretKey(
    Uint8Array.from(JSON.parse(readFileSync(keypairPath, "utf8"))),
  );
  const entry = pickEntry(ledgerPath, pickId);
  const hash = hashOf(entry);
  // The memo carries the integrity hash AND a readable summary, so the pick is
  // legible on a block explorer while the hash keeps it tamper-proof. The
  // verifier matches on the `<prefix>:<hash>` portion, so the readable tail is
  // cosmetic. `|` is stripped from user fields (it's our field delimiter).
  const clean = (s) => String(s).replace(/[|]/g, "/").slice(0, 80);
  const probPart = typeof entry.prob === "number" ? ` @${Math.round(entry.prob * 100)}%` : "";
  const memo = `${PREFIX}:${hash} | ${clean(entry.pick)}${probPart} — ${clean(entry.market)} (${clean(entry.date)})`;

  const connection = new Connection(RPC, "confirmed");
  const ix = new TransactionInstruction({
    keys: [{ pubkey: payer.publicKey, isSigner: true, isWritable: false }],
    programId: MEMO_PROGRAM,
    data: Buffer.from(memo, "utf8"),
  });
  const sig = await sendAndConfirmTransaction(connection, new Transaction().add(ix), [payer]);
  console.log(
    JSON.stringify(
      { pickId: entry.id, market: entry.market, pick: entry.pick, sha256: hash, tx: sig, solscan: `https://solscan.io/tx/${sig}` },
      null,
      2,
    ),
  );
}

async function verify(ledgerPath, pickId, txSig) {
  const entry = pickEntry(ledgerPath, pickId);
  const expected = `${PREFIX}:${hashOf(entry)}`;
  const connection = new Connection(RPC, "confirmed");
  const tx = await connection.getParsedTransaction(txSig, { maxSupportedTransactionVersion: 0 });
  if (!tx) throw new Error("transaction not found");
  // The memo lives in the instruction data (v1 does not echo it into the logs).
  // Collect every candidate: parsed memo strings plus base58-decoded raw data.
  const candidates = [];
  for (const ix of tx.transaction.message.instructions) {
    if (typeof ix.parsed === "string") candidates.push(ix.parsed);
    if (ix.data) {
      try {
        candidates.push(Buffer.from(bs58.decode(ix.data)).toString("utf8"));
      } catch {
        /* not base58 */
      }
    }
  }
  candidates.push(...(tx.meta?.logMessages ?? []));
  const match = candidates.some((c) => c.includes(expected));
  const blockTime = tx.blockTime ? new Date(tx.blockTime * 1000).toISOString() : null;
  console.log(
    JSON.stringify(
      { pickId: entry.id, expectedMemo: expected, onChainMatch: match, blockTime, verdict: match ? "VERIFIED: this exact pick existed on-chain at blockTime" : "MISMATCH: memo does not match this entry" },
      null,
      2,
    ),
  );
  process.exit(match ? 0 : 1);
}

const [, , cmd, ...args] = process.argv;
try {
  if (cmd === "attest" && args.length === 2) await attest(args[0], args[1]);
  else if (cmd === "verify" && args.length === 3) await verify(args[0], args[1], args[2]);
  else {
    console.error("usage: attest.mjs attest <ledger.json> <pickId> | verify <ledger.json> <pickId> <txSig>");
    process.exit(2);
  }
} catch (e) {
  console.error("FAILED:", e.message);
  process.exit(1);
}
