import requests
import time
import random
from .arc4 import EamuseARC4
from kbinxml import KBinXML
import xml.etree.ElementTree as ET
import json
import os
import sys

# 加密密钥
INTERNAL_KEY = "69D74627D985EE2187161570D08D93B12455035B6DF0D8205DF5"

# 请求XML模板
INQUIRE_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<call model="KFC:J:G:A:2025042202" srcid="{}" tag="11451419">
    <cardmng cardid="{}" cardtype="1" method="inquire" update="0"/>
</call>"""

SCORE_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<call model="KFC:J:G:A:2025042202" srcid="{}" tag="11451419">
    <game k="6b4805cc0b8a0ce65aaf62cbcf892e89" method="sv{}_load_m" ver="0">
        <refid __type="str">{}</refid>
    </game>
</call>"""

class Client:
    def __init__(self, server_url):
        self.server_url = server_url
        if not self.server_url.startswith("http://") and not self.server_url.startswith("https://"):
            self.server_url = "http://" + self.server_url
        self.session = requests.Session()
        
    def generate_eamuse_info(self):
        """Generate X-Eamuse-Info header"""
        timestamp = int(time.time())
        random_part = random.randint(0x0000, 0xFFFF)
        return f"1-{timestamp:08x}-{random_part:04x}"
    
    def encrypt_request(self, xml_data, eamuse_info):
        """Encrypt XML data using ARC4"""
        key = bytes.fromhex(eamuse_info[2:].replace("-", ""))
        return EamuseARC4(key).encrypt(xml_data)
    
    def send_request(self, xml_template, endpoint):
        """Send a generic eamuse request"""
        try:
            # Generate headers
            eamuse_info = self.generate_eamuse_info()
            xml_data = KBinXML(xml_template.encode('utf-8')).to_binary()
            encrypted_data = self.encrypt_request(xml_data, eamuse_info)

            
            headers = {
                'X-Eamuse-Info': eamuse_info,
                'User-Agent': 'EAMUSE.XRPC/1.0',
                'Content-Length': str(len(encrypted_data)),
                'X-Compress': 'none'
            }
            
            # Send request
            url = f"{self.server_url}{endpoint}"
            
            response = self.session.post(url, data=encrypted_data, headers=headers)
            
            if response.status_code == 200:
                try:
                    # Check if response is encrypted by looking for X-Eamuse-Info header
                    response_eamuse_info = response.headers.get('X-Eamuse-Info')
                    
                    if response_eamuse_info:
                        # Response is encrypted, decrypt it
                        decrypt_key = bytes.fromhex(response_eamuse_info[2:].replace("-", ""))
                        decrypted = EamuseARC4(decrypt_key).decrypt(response.content)
                    else:
                        # Response is not encrypted, use raw content
                        decrypted = response.content
                    
                    # Try to parse as KBinXML and convert to readable XML
                    try:
                        kbin = KBinXML(decrypted)
                        readable_xml = kbin.to_text()
                        if isinstance(readable_xml, bytes):
                            readable_xml = readable_xml.decode('utf-8')
                        return readable_xml
                    except Exception:
                        text_response = decrypted.decode('utf-8', errors='ignore')
                        return text_response
                        
                except Exception:
                    print("Failed to process response")
                    return None
            else:
                print(f"Error: HTTP {response.status_code}")
                print(f"Response content: {response.text}")
                return None
                
        except Exception as e:
            print(f"Error: {e}")
            return None

    def get_refid(self, card_no, pcbid="00010203040506070809"):
        response = self.send_request(INQUIRE_TEMPLATE.format(pcbid, card_no), "/?model=KFC:J:G:A:2025052700&f=cardmng.inquire")
        if response:
            try:
                root = ET.fromstring(response.encode('utf-8'))
                cardmng = root.find('cardmng')
                refid = cardmng.get('refid')
                return refid
            except Exception as e:
                return None
        return None


    def get_score(self, refid, pcbid="00010203040506070809", version=6):
        response = self.send_request(SCORE_TEMPLATE.format(pcbid, version, refid), "/?model=KFC:J:G:A:2025052700&f=game.sv{}_load_m".format(version))
        if response:
            try:
                root = ET.fromstring(response.encode('utf-8'))
                
                records = []
                
                for info in root.findall('.//info'):
                    param = info.find('param')
                    if param is not None:
                        values = param.text.strip().split()
                        records.append(values)
                
                print(f"查询到 {len(records)} 条记录")
                return records
            except Exception as e:
                print("解析返回数据时出错", e)
                return None
        print("服务器没有返回分数数据")
        return None
    
def convert_to_asphyxia_format(records):
    current_timestamp = int(time.time() * 1000)
    asphyxia_records = []
    
    for i, record in enumerate(records, 1):
        _id = str(i).zfill(16)
        
        asphyxia_record = {
            "collection": "music",
            "mid": int(record[0]),
            "type": int(record[1]),
            "score": int(record[2]),
            "exscore": int(record[3]),
            "clear": int(record[4]),
            "grade": int(record[5]),
            "buttonRate": int(record[8]),
            "longRate": int(record[9]),
            "volRate": int(record[10]),
            "__s": "plugins_profile",
            "__refid": "FILL7YOUR7REFID7",
            "_id": _id,
            "createdAt": {"$$date": current_timestamp},
            "updatedAt": {"$$date": current_timestamp}
        }
        asphyxia_records.append(asphyxia_record)
    
    return asphyxia_records

def main():
    print("此工具用于从sdvx六代私网导出存档并保存为氧无格式")
    print()
    server_url = input("输入需要导出存档的服务器地址: ")
    client = Client(server_url)
    print()

    card_no = input("输入需要查询的账号卡号: ")
    print("开始查询账号信息……")
    refid = client.get_refid(card_no)
    if not refid:
        print("获取账号信息失败")
        return
    
    print("获取到账号的refid: {}".format(refid))
    print("开始查询分数……")
    records = client.get_score(refid)
    if not records:
        print("获取分数失败")
        return
    print()

    print("查询成功，开始转为氧无存档……")
    asphyxia_records = convert_to_asphyxia_format(records)
    if getattr(sys, 'frozen', False):
        application_path = os.path.dirname(sys.executable)
    elif __file__:
        application_path = os.path.dirname(__file__)
    
    with open(os.path.join(application_path, 'sdvx@asphyxia.db'), 'w', encoding='utf-8') as f:
        f.write('{"$$indexCreated":{"fieldName":"__s"}}\n{"$$indexCreated":{"fieldName":"__refid"}}\n')
        for record in asphyxia_records:
            f.write(json.dumps(record, ensure_ascii=False, separators=(',', ':')) + '\n')
    print(f"成功转换并保存 {len(asphyxia_records)} 条记录到 sdvx@asphyxia.db")
    print("可以使用记事本将FILL7YOUR7REFID7替换为你实际的refid，如果只需要进行存档迁移则不需要替换")
    print()

if __name__ == "__main__":
    main()
    a = input("按回车键退出")
    print(a)