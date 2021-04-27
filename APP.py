import asyncio
import base64
import hashlib
import hmac
import json
import urllib
import aiohttp
import requests
from lxml import etree
import random
import settings
import re
from functools import partial
from datetime import datetime
import time
import settings

TEXT_STRING_ZHAOBIAO = '''【{}】\n\n- [招标项目的建设地点]：{}\n\n- [工程规模]：{}\n\n- [招标人]：{}\n\n- [联系人]：{}\n\n- 电话：{}'''
TEXT_STRING_ZHONGBIAO = '''【{}】\n\n- [建设单位]：{}\n\n- [中标单位]：{}'''


class Application:

    def __init__(self):
        self.headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
            'Accept-Encoding': 'gzip, deflate',
            'Accept-Language': 'zh-CN,zh;q=0.9,zh-TW;q=0.8,en-US;q=0.7,en;q=0.6',
            'Cache-Control': 'max-age=0',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Host': 'ztb.xjjs.gov.cn',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.182 Safari/537.36'
        }
        self.city = settings.CITY_INFO


    async def __getContent(self, semaphore, link_):
        conn = aiohttp.TCPConnector(verify_ssl=False)
        async with semaphore:
            async with aiohttp.ClientSession(headers=self.headers, connector=conn, trust_env=True) as session:
                try:
                    async with session.get(link_, timeout=60) as resp:
                        content = await resp.text()
                        return content,link_
                except Exception as e:
                    print(e)
                    return None, None

    def callback4index(self, feature):
        result, link = feature.result()
        if not result:
            return
        html = etree.HTML(result)

        # for link_ in html.xpath("//td[contains(text(), '[{}]')]/../td[2]/a".format(datetime.now().date())):
        for link_ in html.xpath("//td[contains(text(), '[2021-03-12]')]/../td[2]/a"):
            link = "http://ztb.xjjs.gov.cn" + link_.xpath("@href")[0].replace("//", "/")
            city = "".join(link_.xpath("font/text()")).strip("[").strip("]")
            self.project_link.append((link, city))

        # if not self.project_link:
        #     webHook = settings.DINGDING_ITEM.get(city)[1]
        #     secret = settings.DINGDING_ITEM.get(city)[0]
        #     sendText = "今日无新公布中标信息."
        #     self.sendMessage(secret, webHook, sendText, link)

    def callback4detail2zhaobiao(self, city, feature):
        result, link = feature.result()
        html = etree.HTML(result)
        # 招标标题
        title = html.xpath("string(//*[@id='lblTitle'])")[0]
        # # 招标条件
        # condtion = html.xpath("string(//td[@id='TDContent']//table/tr[1]/td/div/p[2])")
        # 建设地点
        add = html.xpath("string(//p[contains(text(), '本次招标项目的建设地点')])").split("：")[-1].strip()
        # 工程规模
        gcgm = html.xpath("string(//p[contains(text(), '工程规模：')])").split("：")[-1].strip()
        # 招标人
        zbr = html.xpath("string(//div[contains(text(), '招 标 人：')]/../following-sibling::td[1])").split("：")[-1].strip()
        # 联系人
        lxr = html.xpath("string(//div[contains(text(), '联 系 人：')]/../following-sibling::td[1])").split("：")[-1].strip()
        # 联系电话
        phone = html.xpath("string(//div[contains(text(), '电 话：')][1]/../following-sibling::td[1])").split("：")[-1].strip()

        sendText = TEXT_STRING_ZHAOBIAO.format(title, add, gcgm, zbr, lxr, phone)
        dingding_city = self.city.get(city)
        if not dingding_city:
            dingding_city = "新疆"

        webHook = settings.DINGDING_ITEM.get(dingding_city)[1]
        secret = settings.DINGDING_ITEM.get(dingding_city)[0]
        self.sendMessage(secret, webHook, sendText, link)



    def callback4detail2zhongbiao(self, city, feature):
        result, link = feature.result()
        html = etree.HTML(result)
        # 招标标题
        title = html.xpath("string(//*[@id='tdTitle']/font[1])").strip()
        # 建设单位
        jsdw = html.xpath("string(//div[contains(text(), '建设单位')]/../following-sibling::td[1])").split("：")[-1].strip()
        # # 中标工程范围
        # zbgcfw = html.xpath("string(//div[contains(text(), '中标工程范围')]/../following-sibling::td[1])").split("：")[-1].strip()
        # 中标单位
        zbdw = html.xpath("string(//div[contains(text(), '单位名称')][1]/../following-sibling::td[1])").split("：")[-1].strip()

        sendText = TEXT_STRING_ZHONGBIAO.format(title, jsdw, zbdw)
        dingding_city = self.city.get(city)
        if not dingding_city:
            dingding_city = "新疆"
        webHook = settings.DINGDING_ITEM.get(dingding_city)[1]
        secret = settings.DINGDING_ITEM.get(dingding_city)[0]
        self.sendMessage(secret, webHook, sendText, link)

    async def taskManager(self, linkItem, callbackFunc, detail=False):
        tasks = []
        semaphore = asyncio.Semaphore(settings.SEMNUM)
        if not detail:
            for link_ in linkItem:
                task = asyncio.ensure_future(self.__getContent(semaphore, link_))
                task.add_done_callback(callbackFunc)
                tasks.append(task)
        else:
            for link, city in linkItem:
                task = asyncio.ensure_future(self.__getContent(semaphore, link))
                task.add_done_callback(partial(callbackFunc, city))
                tasks.append(task)

        await asyncio.gather(*tasks)

    def sendMessage(self, secret, webHook, sendText, imgUrl):
        '''
        使用钉钉机器人向钉钉发送消息
        :param secret:机器人的 secret
        :param webHook: 机器人的 webHook
        :param sendText: 发送的文字
        :param imgUrl: 查看全部的url，即img2url生成的图片
        :return:
        '''
        # 使用钉钉机器人发送定制消息
        timestamp = str(round(time.time() * 1000))
        secret_enc = secret.encode('utf-8')
        string_to_sign = '{}\n{}'.format(timestamp, secret)
        string_to_sign_enc = string_to_sign.encode('utf-8')
        hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        webhook = "{}&timestamp={}&sign={}".format(webHook, timestamp, sign)
        headers = {"Content-Type": "application/json",
                   "Charset": "UTF-8"}

        # 消息类型和数据格式参照钉钉开发文档
        data = {
            "actionCard": {
                "title": "信息公告",
                "text": sendText,
                "btnOrientation": "0",
                "singleTitle": "查看详情" if imgUrl else "",
                "singleURL": imgUrl,
            },
            "msgtype": "actionCard"
        }

        r = requests.post(webhook, data=json.dumps(data), headers=headers)

    def startCrawler4ZhaoBiao(self):
        self.project_link = []
        loop_index_page = asyncio.get_event_loop()
        loop_index_page.run_until_complete(self.taskManager(settings.ZHAOBIAO_URL_ITEM, self.callback4index))

        if self.project_link:
            loop_detail_page = asyncio.get_event_loop()
            loop_detail_page.run_until_complete(self.taskManager(self.project_link, self.callback4detail2zhaobiao, detail=True))

    def startCrawler4ZhongBiao(self):
        self.project_link = []
        loop_index_page = asyncio.get_event_loop()
        loop_index_page.run_until_complete(self.taskManager(settings.ZHONGBIAO_URL_ITEM, self.callback4index))

        if self.project_link:
            loop_detail_page = asyncio.get_event_loop()
            loop_detail_page.run_until_complete(self.taskManager(self.project_link, self.callback4detail2zhongbiao, detail=True))


if __name__ == '__main__':
    app = Application()
    app.startCrawler4ZhaoBiao()
    app.startCrawler4ZhongBiao()