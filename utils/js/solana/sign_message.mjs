import nacl from "tweetnacl";
import naclUtil from "tweetnacl-util";
import bip39 from "bip39";
import {derivePath} from "ed25519-hd-key";
import {Keypair} from "@solana/web3.js";
import bs58 from "bs58";


async function signSolMessage(mnemonic, message, encoding) {
    const seed = await bip39.mnemonicToSeed(mnemonic);
    const derivationPath = "m/44'/501'/0'/0'";
    const derivedSeed = derivePath(derivationPath, seed.toString('hex')).key;
    const keypair = Keypair.fromSeed(derivedSeed);
    const messageBytes = naclUtil.decodeUTF8(message);
    const signature = nacl.sign.detached(messageBytes, keypair.secretKey);
    if (encoding === '58'){
        return bs58.encode(signature);
    }
    else {
        return Buffer.from(signature).toString("base64");
    }
}

async function sign_message(mnemonic, message, encoding){
    return await signSolMessage(mnemonic, message, encoding)
}

const mnemonic = process.argv[2];
const message = process.argv[3];
const encoding = process.argv[4];

process.stdout.write(JSON.stringify(await sign_message(mnemonic, message, encoding)))
