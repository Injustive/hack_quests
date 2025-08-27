import bip39 from 'bip39';
import { derivePath } from 'ed25519-hd-key';
import { Keypair } from '@solana/web3.js';


async function seed_to_address(mnemonic){
  const seed = await bip39.mnemonicToSeed(mnemonic);
  const derivationPath = "m/44'/501'/0'/0'";
  const derivedSeed = derivePath(derivationPath, seed.toString('hex')).key;
  const keypair = Keypair.fromSeed(derivedSeed);
  const address = keypair.publicKey.toBase58();
  return {
    address: address,
  };
}

const mnemonic = process.argv[2];

process.stdout.write(JSON.stringify(await seed_to_address(mnemonic)))
