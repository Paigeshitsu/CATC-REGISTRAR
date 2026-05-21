import sys
import requests
from urllib.parse import urlencode

apikey = 'a49cb936fca6db2dc238e4aba043d59b'
sendername = 'CATC Portal'

def send_message(message, number):
    print('Sending Message...')
    params = {
        'apikey': apikey,
        'sendername': sendername,
        'message': message,
        'number': number
    }
    path = 'https://semaphore.co/api/v4/messages?' + urlencode(params)
    response = requests.post(path)
    if response.status_code == 200:
        print('Message Sent!')
    else:
        print(f'Failed to send message: {response.status_code} - {response.text}')

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python send_sms.py 'message' 'number'")
        sys.exit(1)
    message = sys.argv[1]
    number = sys.argv[2]
    send_message(message, number)
