import mlflow
import os
from PIL import Image
import io
import json
from datetime import datetime

class MLflowService:
    def __init__(self, experiment_name="comfyui-image-processing"):
        """Initialize MLflow tracking"""
        mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000"))
        self.experiment = mlflow.set_experiment(experiment_name)
    
    def log_image_generation(self, input_image, output_image, workflow_config, metrics=None):
        """Log an image generation experiment
        
        Args:
            input_image: PIL Image or path to input image
            output_image: PIL Image or path to output image
            workflow_config: Dict containing workflow configuration
            metrics: Optional dict of metrics to log
        """
        with mlflow.start_run():
            # Log parameters (workflow configuration)
            mlflow.log_params(workflow_config)
            
            # Log input image
            if isinstance(input_image, str):
                mlflow.log_artifact(input_image, "input_image")
            else:
                buf = io.BytesIO()
                input_image.save(buf, format='PNG')
                mlflow.log_image(buf.getvalue(), "input_image.png")
            
            # Log output image
            if isinstance(output_image, str):
                mlflow.log_artifact(output_image, "output_image")
            else:
                buf = io.BytesIO()
                output_image.save(buf, format='PNG')
                mlflow.log_image(buf.getvalue(), "output_image.png")
            
            # Log workflow definition
            mlflow.log_dict(workflow_config, "workflow_config.json")
            
            # Log metrics if provided
            if metrics:
                mlflow.log_metrics(metrics)
            
            # Log generation timestamp
            mlflow.log_param("generation_timestamp", datetime.now().isoformat())
    
    def log_model_version(self, model_name, model_path, workflow_config):
        """Log a new model version
        
        Args:
            model_name: Name of the model
            model_path: Path to model checkpoint
            workflow_config: ComfyUI workflow configuration
        """
        with mlflow.start_run():
            # Log model files
            mlflow.log_artifact(model_path, "model")
            
            # Log model configuration
            mlflow.log_dict(workflow_config, "workflow_config.json")
            
            # Register model version
            mlflow.register_model(f"runs:/{mlflow.active_run().info.run_id}/model", model_name)
    
    def get_best_workflow(self, metric_name="quality_score", max_results=5):
        """Get best performing workflows based on metric
        
        Args:
            metric_name: Metric to sort by
            max_results: Maximum number of results to return
        
        Returns:
            List of (run_id, workflow_config, metric_value)
        """
        client = mlflow.tracking.MlflowClient()
        
        # Get all runs for the experiment
        runs = client.search_runs(
            experiment_ids=[self.experiment.experiment_id],
            filter_string=f"metrics.{metric_name} IS NOT NULL",
            order_by=[f"metrics.{metric_name} DESC"],
            max_results=max_results
        )
        
        results = []
        for run in runs:
            run_id = run.info.run_id
            metric_value = run.data.metrics.get(metric_name)
            
            # Get workflow config
            workflow_path = client.download_artifacts(run_id, "workflow_config.json")
            with open(workflow_path) as f:
                workflow_config = json.load(f)
            
            results.append((run_id, workflow_config, metric_value))
        
        return results
