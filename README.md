# iKuai GeoIP Sync

把中国指定城市的IP段定时同步到爱快路由器的IP分组（IP/MAC分组管理）。

## 功能
- 从 [metowolf/iplist](https://github.com/metowolf/iplist) 抓取按行政区划代码组织的城市IP段
- 每月自动同步一次（cron 可配），也可手动触发
- 单组超过 N 条自动拆成 `大连`、`大连2`、`大连3`...
- 简单 Web UI：状态、立即同步、查看日志

## 默认配置
- 城市：大连（210200）
- 每组上限：800 条 CIDR
- 同步周期：每月11号 04:00（Asia/Shanghai）
- 端口：8765

## 部署
1. 复制 `.env.example` → `.env`，填写爱快账号密码和城市代码
2. `docker compose up -d --build`
3. 浏览器打开 `http://<host>:8765`

## 城市代码
见 https://github.com/metowolf/iplist/blob/master/docs/cncity.md
