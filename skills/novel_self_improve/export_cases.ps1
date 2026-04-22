param(
    [string]$Db = "data/novel_flow.db",
    [string]$OutputDir = "evals/romance/exported_cases/latest",
    [int]$Limit = 20,
    [string]$SampleMode = "low_score"
)

python -m tools.export_eval_cases --db $Db --output-dir $OutputDir --limit $Limit --sample-mode $SampleMode
