import os

import sagemaker
from sagemaker.huggingface import HuggingFace


def main() -> None:
    session = sagemaker.Session()
    role = os.environ["SAGEMAKER_ROLE_ARN"]
    bucket = os.getenv("SAGEMAKER_BUCKET", session.default_bucket())
    prefix = os.getenv("SAGEMAKER_PREFIX", "profuturo/fine_tuning")

    train_s3_uri = os.getenv("S3_TRAIN_URI", f"s3://{bucket}/{prefix}/data/train.jsonl")
    output_s3_uri = os.getenv("S3_OUTPUT_URI", f"s3://{bucket}/{prefix}/output")
    job_name = os.getenv("SAGEMAKER_JOB_NAME", "profuturo-qwen25-3b-ft")

    estimator = HuggingFace(
        entry_point=os.getenv("SAGEMAKER_ENTRYPOINT", "train.py"),
        source_dir=os.getenv("SAGEMAKER_SOURCE_DIR", "training"),
        role=role,
        instance_count=int(os.getenv("SAGEMAKER_INSTANCE_COUNT", "1")),
        instance_type=os.getenv("SAGEMAKER_INSTANCE_TYPE", "ml.g5.2xlarge"),
        transformers_version=os.getenv("SAGEMAKER_TRANSFORMERS_VERSION", "4.46"),
        pytorch_version=os.getenv("SAGEMAKER_PYTORCH_VERSION", "2.4"),
        py_version=os.getenv("SAGEMAKER_PY_VERSION", "py311"),
        output_path=output_s3_uri,
        hyperparameters={
            "model_name": "Qwen/Qwen2.5-3B-Instruct",
            "train_file": train_s3_uri,
            "max_steps": int(os.getenv("TRAIN_MAX_STEPS", "300")),
            "learning_rate": float(os.getenv("TRAIN_LR", "2e-5")),
            "per_device_train_batch_size": int(os.getenv("TRAIN_BATCH_SIZE", "1")),
            "gradient_accumulation_steps": int(os.getenv("TRAIN_GRAD_ACC", "8")),
        },
    )

    estimator.fit({"train": train_s3_uri}, job_name=job_name, wait=False)
    print(f"Training job lanzado: {job_name}")


if __name__ == "__main__":
    main()
