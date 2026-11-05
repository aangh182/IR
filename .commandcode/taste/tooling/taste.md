# Tooling

- Doesn't want notebook driver scripts (Colab/Kaggle `.ipynb`) kept in the repo once his own machine can handle the job — he asked for them deleted so the work is runnable by him locally via the CLI instead. Confidence: 0.65
- Heavy batch jobs (e.g. embedding the whole corpus) belong on Kaggle as a self-contained `.ipynb` he can upload zipped artifacts to, not run locally; keep the notebook free of repo imports and use the local machine only for light smoke tests. Whether notebooks stay in the repo depends on whether local can do the job. He'll accept duplicated embed/index logic in the notebook as the price of that independence — no repo import, no vendored `src/` in the upload. Confidence: 0.7
- Superseded: he previously favored Kaggle notebooks over Colab for large (~100GB) GPU indexing runs; the "delete the notebooks, I'll run it on my machine" request cut against that, so treat the Colab-vs-Kaggle distinction as legacy context only. Confidence: 0.35
