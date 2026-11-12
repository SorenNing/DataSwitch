# 数据切换 · DataSwitch

适用于越狱 iOS 16 / 17 的独立控制中心模块。通过 CCSupport 在系统「设置 → 控制中心」添加，包标识 `com.ning.dataswitch`，版本 `1.0`。

- 轻点或长按按钮展开「数据切换」卡片。
- 两条线路显示真实运营商名称以及「使用中 / 未选用」状态，胶囊与名称整组居中。
- 选择线路通过 CoreTelephony 切换默认蜂窝数据。操作失败显示在卡片内。
- 控制中心沿用选定的 C「环绕单卡」透明白图，设置列表与 Sileo 使用已确认的蓝色配套图标。
- 主按钮画布 46pt，对应可见图形约 35.6pt；按蜂窝管理参考图形约 35.3pt换算。展开图标保持 32pt。

## 实现与依赖

使用系统 `CCUIContentModule` / `CCUIContentModuleContentViewController`，通过 `requestExpandModule` 展开。模块无需安装 ControlCenter18，也不打包原 CCSwitchData 二进制、注入库或 SIM 启停工具。

原功能参考 Netskao 的 `CCSwitchDataModule`。重建后的四份 Objective-C 源码均在 `src/`。运营商优先按订阅的 PLMN 查询，回退到 UUID 匹配的运营商数据；不将可编辑 SIM 标签作为运营商。

选中状态使用 `getCurrentDataSubscriptionContextSync:` 的实际返回；无法读取时显示「状态未知」。切换使用带 `userDataPreferred = @YES` 的订阅上下文调用 `setActiveUserDataSelection:error:`。该 setter 返回 `void`：无错误只代表请求未被立即拒绝，卡片不伪造已切换状态；再次展开从系统读取实际线路。自动数据切换、无服务、双 eSIM 及切换生效延迟仍需真机验证。

## 本地检查

```sh
python3 tools/check_local.py
python3 tools/selftest.py
python3 tools/package.py --dry-run
```

这些命令只核查源码、元数据、图标与打包计划。不会编译 iOS 程序或触发 Actions。

## 构建

唯一工作流为手动 `workflow_dispatch`，使用 `macos-latest` Apple iPhoneOS SDK 编译 arm64 / arm64e、合并并签名。每轮构建需用户授权。

```sh
bash tools/build-macos.sh
```

最终文件：`dist/com.ning.dataswitch_1.0_iphoneos-arm64e.deb` 与 `dist/package-validation.json`。打包使用 Python raw USTAR + gzip + ar，不调用 macOS ar。验证器核对 arm64e ABI、chained fixups、每页代码签名、三处九项图标以及全部安装路径。

作者与维护：Ning&Netskao。原功能来源和资源哈希见 `share/doc/com.ning.dataswitch/provenance.json`。
