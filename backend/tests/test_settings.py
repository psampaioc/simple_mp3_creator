from app.settings import piper_model_path_for_locale


def test_piper_model_path_follows_project_locale() -> None:
    assert piper_model_path_for_locale("en-US").endswith("en_US-amy-low.onnx")
    assert piper_model_path_for_locale("pt-BR").endswith("pt_BR-cadu-medium.onnx")
