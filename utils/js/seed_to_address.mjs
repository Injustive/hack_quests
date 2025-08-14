import * as bip39 from "bip39";
import * as bitcoin from "bitcoinjs-lib";
import { BIP32Factory } from "bip32";
import * as ecc from "tiny-secp256k1";

function seed_to_address(mnemonic){
  const bip32 = BIP32Factory(ecc);
  const seed = bip39.mnemonicToSeedSync(mnemonic);
  const hdKey = bip32.fromSeed(seed, bitcoin.networks.bitcoin);
  const path = "m/84'/0'/0'/0/0";
  const child = hdKey.derivePath(path);
  const { address } = bitcoin.payments.p2wpkh({
    pubkey: child.publicKey,
    network: bitcoin.networks.bitcoin,
  });
  return {
    address: address,
    wif: child.toWIF(),
  };
}

const mnemonic = process.argv[2];

process.stdout.write(JSON.stringify(seed_to_address(mnemonic)))
