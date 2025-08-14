import {Signer} from "./bip322-js/dist/index.js";

function sign_message_bip322(wif, address, message){
    return Signer.sign(wif, address, message);
}


const wif = process.argv[2];
const address = process.argv[3];
const message = process.argv[4];

process.stdout.write(JSON.stringify(sign_message_bip322(wif, address, message)))
