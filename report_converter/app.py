import email, io, json, base64, zipfile, urllib
import boto3
import xmltodict

from dmarc_reports.classes import AggregateReport
from dmarc_reports.exceptions import BadAggregateReport

s3 = boto3.client('s3')

def lambda_handler(event, context):
    obj = event['getObjectContext']
    res = urllib.request.urlopen(obj['inputS3Url'])
    
    mail_data = res.read()
    mail = email.message_from_bytes(mail_data)
    
    report = get_report(mail)

    # AggregateReportの機能ではなくinitによるバリデーションを期待している
    try:
        AggregateReport(io.StringIO(report))
    except BadAggregateReport as error:
        return invalid_data_format_post_process("Invalid format report", obj)
    except Exception as error:
        return invalid_data_format_post_process("This Data cannot be converted", obj)
    
    json_mailbody = xmltodict.parse(report)
    shaped_dmarc_json(json_mailbody)

    return s3.write_get_object_response(
        RequestRoute=obj['outputRoute'],
        RequestToken=obj['outputToken'],
        Body=str(json.dumps(json_mailbody))
    )
    
    return {
        "statusCode": 200,
        "body": "Success",
    }

def get_report(mail):
    
    '''
        Emailオブジェクトからレポートを抽出する
    '''
    raw_payload = mail.get_payload()
    if mail.get('Content-Transfer-Encoding') == 'base64':
        payload = base64.b64decode(raw_payload)

    match mail.get_content_type():
        case 'application/zip':
            z = zipfile.ZipFile(io.BytesIO(payload))
            return z.read(z.namelist()[0]).decode('utf-8')
        case 'application/gzip':
            return ""
        case _:
            return raw_payload

def shaped_dmarc_json(data):
    '''
        受け取ったJSON形式のDMARCレポートを整形する
    '''
    # Convert 'Record' to list if dict
    if type(data['feedback']['record']) is not list:
        data['feedback']['record'] = [data['feedback']['record']]

    # Convert 'dkim' to list if dict
    for i,d in enumerate(data['feedback']['record']):
        if 'auth_results' in d:
            if 'dkim' in d['auth_results'] and type(d['auth_results']['dkim']) is not list:
                data['feedback']['record'][i]['auth_results']['dkim'] = [data['feedback']['record'][i]['auth_results']['dkim']]

def invalid_data_format_post_process(msg, obj):
    '''
        不正なデータ形式を得た場合の共通終了処理
        該当ケースでは通常この返却値をメインハンドラでreturnして終了する
    '''
    print(msg)
    
    #NOTE: 何もレスポンスに書き込まず終了すると無限に再施行される？
    s3.write_get_object_response(
        RequestRoute=obj['outputRoute'],
        RequestToken=obj['outputToken'],
        Body=str(json.dumps({}))
    )
    return {
        "StatsuCode": 400,
        "Body": msg
    }
