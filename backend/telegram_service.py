"""Optional private-chat transport. Never log bot URLs/tokens or retry a send."""
import requests
from .telegram_config import bot_settings


class TelegramError(Exception):
    def __init__(self,code,uncertain=False):
        self.code,self.uncertain=code,uncertain
        super().__init__(code)


def telegram_call(method,payload,config,pdf=None):
    config=bot_settings(config)
    token=config.get('TELEGRAM_BOT_TOKEN')
    if not token:raise TelegramError('TELEGRAM_NOT_CONFIGURED')
    transport=config.get('TELEGRAM_TRANSPORT')
    if transport:return transport(method,payload,pdf)
    response=None
    sending=method in ('sendMessage','sendDocument')
    try:
        kwargs={'timeout':(5,25),'allow_redirects':False}
        if pdf is None:kwargs['json']=payload
        else:kwargs.update(data=payload,files={'document':('voucher.pdf',pdf,'application/pdf')})
        response=requests.post('https://api.telegram.org/bot'+token+'/'+method,**kwargs)
        if response.status_code>=500:raise TelegramError('TELEGRAM_UNAVAILABLE',sending)
        if response.status_code!=200:raise TelegramError('TELEGRAM_REJECTED')
        value=response.json()
        if not isinstance(value,dict) or value.get('ok') is not True:raise TelegramError('TELEGRAM_REJECTED')
        return value['result']
    except TelegramError:raise
    except (requests.RequestException,ValueError,KeyError):
        raise TelegramError('TELEGRAM_UNCERTAIN' if sending else 'TELEGRAM_UNAVAILABLE',sending) from None
    finally:
        if response is not None:response.close()
