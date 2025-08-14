import re
from enum import Enum


class Proxy:
    def __init__(self, proxy: str | None):
        self.proxy = proxy
        self.validate()

    def __bool__(self):
        return bool(self.proxy)

    @property
    def session_proxy(self):
        if self.proxy:
            return {
                'http': f'http://{self.proxy}',
                'https': f'http://{self.proxy}'
            }

    @property
    def w3_proxy(self):
        if self.proxy:
            return f'http://{self.proxy}'

    def __getattr__(self, item):
        return self.__dict__[item] if self.__dict__['proxy'] else None

    def validate(self):
        if self.proxy:
            pattern = r'^.+:.+@.+:\d+$'
            if not re.fullmatch(pattern, self.proxy):
                raise ValueError('Proxy format is not valid', self.proxy)

    def __repr__(self):
        return f'Proxy <{self.proxy}>' if self.proxy else 'No proxy found'


class RpcProviders(Enum):
    ETH = 'https://eth.llamarpc.com'
    BSC = 'https://rpc.ankr.com/bsc/0e222c5c9732e39bde6d28fcf7a76694c2e19b6e5460aa29b74d6a8b6c76b0bb'
    OPBNB = 'https://opbnb-rpc.publicnode.com'
    POLYGON = 'https://rpc.ankr.com/polygon/'
    LINEA = 'https://rpc.linea.build'
    MANTLE = 'https://rpc.ankr.com/mantle/0e222c5c9732e39bde6d28fcf7a76694c2e19b6e5460aa29b74d6a8b6c76b0bb'
    LAMINA = 'https://subnets.avax.network/lamina1id/mainnet/rpc'
    MORPH_TESTNET = 'https://rpc-holesky.morphl2.io/'
    PLUME_TESTNET = 'https://testnet-rpc.plumenetwork.xyz/http'
    BSC_TESTNET = 'https://bsc-testnet.public.blastapi.io'
    OG_TESTNET = 'https://rpc-nitro.0g.ai/'
    MOVEMENT_EVM = 'https://mevm.devnet.imola.movementlabs.xyz/'
    OMNI_OMEGA_TESTNET = 'https://omega.omni.network'
    SEPOLIA_TESTNET = 'https://eth-sepolia.public.blastapi.io/'
    ABSTRACT_TESTNET = 'https://api.testnet.abs.xyz/'
    STORY_PROTOCOL_TESTNET = 'https://odyssey.storyrpc.io/'
    ZETACHAIN = 'https://zetachain-evm.blockpi.network/v1/rpc/public'
    XTERIO = 'https://xterio.alt.technology'
    ARBITRUM_MACH = 'https://prettiest-patient-scion.arbitrum-mainnet.quiknode.pro/2d53fa7ffc71e31afb3113f96c54519fcd6516e2'
    OPTIMISM_MACH = 'https://alien-dry-lake.optimism.quiknode.pro/9e3364e544a78fa0581658f542d58d8c02cd13ba'
    BASE_MACH = 'https://polished-spring-star.base-mainnet.quiknode.pro/19455fd433fb2639609315f8588c3a58a5a9a10f'
    ARBITRUM = "https://1rpc.io/arb"
    OPTIMISM = "https://1rpc.io/op"
    BASE = "https://rpc.ankr.com/base/0e222c5c9732e39bde6d28fcf7a76694c2e19b6e5460aa29b74d6a8b6c76b0bb"
    MONAD_TESTNET = "https://testnet-rpc.monad.xyz"
    SAHARA_TESTNET = "https://testnet.saharalabs.ai/"
    CAMP_NETWORK_TESTNET = "https://rpc.basecamp.t.raas.gelato.cloud"
    DOMA_TESTNET = 'https://rpc-testnet.doma.xyz'


class ChainExplorers(Enum):
    ARBITRUM = "https://arbiscan.io/tx/"
    OPTIMISM = "https://optimistic.etherscan.io/tx/"
    BASE = "https://basescan.org/tx/"
    SEPOLIA_TESTNET = "https://sepolia.etherscan.io/tx/"
    MONAD = "https://testnet.monadexplorer.com/tx/"
    BSC = 'https://bscscan.com/tx/'
    OPBNB = 'https://opbnbscan.com/tx/'


class TxStatusResponse(Enum):
    NEED_APPROVE = 'NEED_APPROVE'
    GOOD = 'GOOD'
    COOLDOWN_PERIOD = 'COOLDOWN_PERIOD'
    ALREADY_MINTED = 'ALREADY_MINTED'
    GAS_WARNING = 'GAS_WARNING'
    STATUS_ZERO = 'STATUS_ZERO'
    INSUFFICIENT_BALANCE = 'INSUFFICIENT_BALANCE'
