## 概要

Athena実行時に直接レポート変換を行いクエリを行うシステム

以下で作成されたシステムの拡張  
https://github.com/cm-suzuki-junya/dmarc-rua-report-searcher

## 詳細

上記記載のリポジトリではメールを受信するたびそのデータをマスタにAthenaクエリ用にJSONに変換抽出したDMARCレポートを保持していた。

本システムでは上記のダブルマスタを不要にする方法としてObject Lambdaを採用し、  
クエリのたびにメールから抽出・変換を行うような外付けの仕組みを作成している。

この方式を採用することで加工データごデータを持つ必要はなくなる一方で、高頻度の検索の場合都度変換処理が行われその結果サービス利用やクエリのレスポンス速度の応答の遅延等のデメリットも発生する。

一長一短かつ試験的に行なったもののため上記リポジトリとは分離し該当のバケットを参照する方式をとっており、その関係で上記システムがすでに利用されていることが前提となる。

詳細は以下参照。


## デプロイ

`.env.example`を参考に事前に`.env`を作成します。  

```bash
sam build
sam deploy --parameter-overrides file://.env
```


## Glueテーブルの作成

LOCATIONには上記で作成されたObject Lambdaアクセスポイントのエイリアスを指定する

```
CREATE EXTERNAL TABLE IF NOT EXISTS dmarc_report_ol (
  feedback struct<
    report_metadata: struct<
      org_name: string,
      email: string,
      extra_contact_info: string,
      report_id: string,
      date_range: struct<
        begin: string,
        `end`: string
      >
    >,
    policy_published: struct<
      domain: string,
      adkim: string,
      aspf: string,
      p: string,
      sp: string,
      pct: string,
      np: string
    >,
    record: array<struct<
      `row`: struct<
        source_ip: string,
        `count`: string,
        policy_evaluated: struct<
          disposition: string,
          dkim: string,
          spf: string
        >
      >,
      identifiers: struct<
        header_from: string
      >,
      auth_results: struct<
        spf: struct<
          domain: string,
          result: string
        >,
        dkim: array<
          struct<
            domain: string,
            result: string,
            selector: string
          >
        >
      >>
    >
  >
 )
ROW FORMAT SERDE 'org.apache.hive.hcatalog.data.JsonSerDe'
WITH SERDEPROPERTIES ('paths'='feedback')
LOCATION 's3://dmarc-convert-functi-xxxxxx--ol-s3/source/catcher/'
```

## Athenaによる検索例

SPFおよびDKIMいずれにも合致しないメールの送信もとIP毎の総和を算出する。  
不正なレポートの場合は空の値(null)が出力される関係で弾かないといけない(良い方法がありそうだが...)

```sql
WITH records AS (
    SELECT feedback.record as record
    FROM dmarc_report
)
SELECT
    rec.row.source_ip,
    SUM(CAST(rec.row.count AS Integer)) AS cnt
FROM records, UNNEST(record) AS t(rec)
WHERE rec.row.policy_evaluated.spf != 'pass' AND rec.row.policy_evaluated.dkim != 'pass'　AND feedback is not null
GROUP BY rec.row.source_ip
ORDER BY cnt desc;
```