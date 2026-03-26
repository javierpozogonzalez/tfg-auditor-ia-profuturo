import subprocess


def main() -> None:
    command = [
        "python",
        "-m",
        "mlx_lm.lora",
        "--train",
        "--model",
        "Qwen/Qwen2.5-3B-Instruct",
        "--data",
        "data",
        "--iters",
        "300",
        "--adapter-path",
        "adapters_profuturo",
    ]
    subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
