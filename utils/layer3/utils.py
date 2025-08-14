from utils.utils import sleep, MaxLenException, get_data_lines, get_session
from utils.models import TxStatusResponse, Proxy
from curl_cffi.requests.errors import RequestsError



def pass_transaction(success_message='NFT MINTED!',
                     excludes=None):
    excludes = [] if not excludes else excludes
    def outer(func):
        async def wrapper(obj, *args, **kwargs):
            logger = obj.logger.bind(func_name=func.__name__, func_module=func.__module__)
            attempts = 10
            completed = False
            while attempts:
                try:
                    if not completed:
                        tx_hash = await func(obj, *args, **kwargs)
                        completed = True
                    await sleep(20, 40)
                    receipts = await obj.client.w3.eth.get_transaction_receipt(tx_hash)
                    status = receipts.get("status")
                    if status == 1:
                        logger.success(f'{success_message}. HASH - {obj.explorer}{tx_hash}')
                        return TxStatusResponse.GOOD, tx_hash
                    else:
                        if '0' in excludes:
                            return TxStatusResponse.ALREADY_MINTED, None
                        logger.error(f'Status {status}. HASH - {obj.explorer}{tx_hash}')
                        attempts -= 1
                except Exception as e:
                    message = str(e)
                    if 'Forbidden' in message:
                        raise
                    elif 'Proxy Authentication Required' in message:
                        raise RequestsError('Proxy Authentication Required')
                    elif '' == message:
                        raise RequestsError('Strange error!')
                    elif '0x76abf214' in message:
                        return TxStatusResponse.ALREADY_MINTED, None
                    if any(exclude in message for exclude in excludes):
                        return TxStatusResponse.ALREADY_MINTED, None
                    logger.error(f'Error! {e}. Trying again...')
                    await sleep(5, 10)
                    attempts -= 1
            else:
                raise RequestsError('Strange error!')
        return wrapper
    return outer