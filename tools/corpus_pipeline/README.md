# Corpus Pipeline

这里存放离线语料维护工具。它们不参与 FastAPI/Vue 应用启动，也不会被后端运行时导入。

## 正式工具

- `extract_all.py`：从 EPUB 提取章节，输出 Markdown + YAML frontmatter。
- `extract_christie_collection.py`：从已检查的阿加莎·克里斯蒂合集 EPUB 中提取八部精选小说，按章节写入 `ac01`–`ac08`。
- `generate_summaries.py`：为 `hp01` 中尚无摘要的章节调用 Proma API 生成摘要。

安装工具依赖：

```powershell
python -m pip install -r tools/corpus_pipeline/requirements.txt
```

先使用只读模式检查目标：

```powershell
python tools/corpus_pipeline/extract_all.py book.epub --dry-run
python tools/corpus_pipeline/extract_christie_collection.py collection.epub --dry-run
python tools/corpus_pipeline/generate_summaries.py --dry-run
```

确认后再写入；也可以显式指定语料目录：

```powershell
python tools/corpus_pipeline/extract_all.py book.epub --corpus-dir corpus
python tools/corpus_pipeline/extract_christie_collection.py collection.epub --corpus-dir corpus
$env:PROMA_API_KEY = "..."
python tools/corpus_pipeline/generate_summaries.py --corpus-dir corpus/hp01
```

提取器会覆盖同名章节文件。执行写入前应检查 `git status`，并确保现有语料修改已经提交。

## Legacy

`legacy/` 保存已经完成历史使命或被替代的一次性脚本：旧版提取器、预写摘要注入脚本和章节切段实验。保留它们是为了复现早期语料加工过程；新数据维护不应继续依赖这些脚本。
