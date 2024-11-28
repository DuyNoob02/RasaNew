from rasa.engine.graph import GraphComponent, ExecutionContext
from rasa.engine.recipes.default_recipe import DefaultV1Recipe
from rasa.engine.storage.resource import Resource
from rasa.engine.storage.storage import ModelStorage
from rasa.shared.nlu.training_data.message import Message
from rasa.shared.nlu.training_data.training_data import TrainingData
from typing import Dict, Text, Any, Optional, List
from sklearn.svm import SVC
from sklearn.feature_extraction.text import TfidfVectorizer
from underthesea import word_tokenize
import numpy as np
import pickle
from dataclasses import dataclass

@dataclass
class SVMClassifierModel:
    """Dataclass để lưu trữ model và metadata"""
    vectorizer_vocabulary: Dict
    training_examples_count: int
    unique_labels: List[str]
    model_data: bytes
    vectorizer_data: bytes

@DefaultV1Recipe.register(
    component_types=DefaultV1Recipe.ComponentType.INTENT_CLASSIFIER,
    is_trainable=True
)
class SVMClassifier(GraphComponent):
    @classmethod
    def required_packages(cls) -> List[Text]:
        return ["sklearn", "underthesea"]

    def __init__(
        self,
        config: Dict[Text, Any],
        model_storage: ModelStorage,
        resource: Resource,
        model: Optional[SVMClassifierModel] = None,
    ) -> None:
        self.config = config
        self.model_storage = model_storage
        self.resource = resource
        self._model = model
        
        if not model:
            self.vectorizer = TfidfVectorizer()
            self.clf = SVC(kernel="linear", probability=True)  # Thêm probability=True để có thể lấy confidence
        else:
            self.vectorizer = pickle.loads(model.vectorizer_data)
            self.clf = pickle.loads(model.model_data)

    @classmethod
    def create(
        cls,
        config: Dict[Text, Any],
        model_storage: ModelStorage,
        resource: Resource,
        execution_context: ExecutionContext,
    ) -> GraphComponent:
        return cls(config, model_storage, resource)

    def preprocess(self, text: Text) -> Text:
        """Preprocess và tokenize text input.
        
        Args:
            text: Input text cần xử lý
            
        Returns:
            Processed text sau khi tokenize
        """
        if text is None:
            return ""
        
        # Chuyển về string nếu không phải
        if not isinstance(text, str):
            text = str(text)
            
        # Loại bỏ khoảng trắng thừa
        text = text.strip()
        
        # Nếu text rỗng, trả về chuỗi rỗng
        if not text:
            return ""
            
        try:
            # Tokenize text
            return word_tokenize(text, format='text')
        except Exception as e:
            print(f"Error in tokenization: {e}")
            # Nếu có lỗi, trả về text gốc
            return text

    def train(self, training_data: TrainingData) -> Resource:
        """Train SVM classifier với training data.
        
        Args:
            training_data: Training data từ Rasa
            
        Returns:
            Resource chứa model đã train
        """
        # Extract training examples và labels
        training_examples = []
        labels = []
        
        for example in training_data.training_examples:
            if example.get("text") is not None and example.get("intent") is not None:
                training_examples.append(example.get("text"))
                labels.append(example.get("intent"))

        if not training_examples:
            raise ValueError("No training examples provided")

        # Tiền xử lý dữ liệu
        processed_examples = [self.preprocess(text) for text in training_examples]
        
        # Loại bỏ các examples rỗng
        valid_examples = []
        valid_labels = []
        for text, label in zip(processed_examples, labels):
            if text.strip():  # Chỉ giữ lại các ví dụ không rỗng
                valid_examples.append(text)
                valid_labels.append(label)

        if not valid_examples:
            raise ValueError("No valid training examples after preprocessing")

        # Vectorize và train model
        X = self.vectorizer.fit_transform(valid_examples)
        y = np.array(valid_labels)
        self.clf.fit(X, y)

        # Tạo model fingerprintable
        classifier_data = SVMClassifierModel(
            vectorizer_vocabulary=self.vectorizer.vocabulary_,
            training_examples_count=len(valid_examples),
            unique_labels=list(set(valid_labels)),
            model_data=pickle.dumps(self.clf),
            vectorizer_data=pickle.dumps(self.vectorizer)
        )

        # Lưu model
        self.persist()

        return classifier_data

    def process(self, messages: List[Message]) -> List[Message]:
        """Process messages để predict intent.
        
        Args:
            messages: List of messages cần xử lý
            
        Returns:
            Processed messages với intent predictions
        """
        for message in messages:
            if not self.clf or not self.vectorizer:
                # Không có model được train
                intent = {"name": None, "confidence": 0.0}
            else:
                # Xử lý text
                text = message.get("text", "")
                processed_text = self.preprocess(text)
                
                if not processed_text.strip():
                    intent = {"name": None, "confidence": 0.0}
                else:
                    try:
                        X = self.vectorizer.transform([processed_text])
                        
                        # Predict
                        intent_name = self.clf.predict(X)[0]
                        # Lấy probability
                        probabilities = self.clf.predict_proba(X)[0]
                        confidence = float(probabilities.max())

                        intent = {"name": intent_name, "confidence": confidence}
                    except Exception as e:
                        print(f"Error in prediction: {e}")
                        intent = {"name": None, "confidence": 0.0}
            
            message.set("intent", intent, add_to_output=True)
        return messages

    def persist(self) -> None:
        """Lưu model và vectorizer."""
        with self.model_storage.write_to(self.resource) as model_dir:
            model_path = model_dir / "model.pkl"
            vectorizer_path = model_dir / "vectorizer.pkl"
            
            with open(model_path, "wb") as f:
                pickle.dump(self.clf, f)
            with open(vectorizer_path, "wb") as f:
                pickle.dump(self.vectorizer, f)

    @classmethod
    def load(
        cls,
        config: Dict[Text, Any],
        model_storage: ModelStorage,
        resource: Resource,
        execution_context: ExecutionContext,
        **kwargs: Any,
    ) -> GraphComponent:
        """Load saved model và vectorizer.
        
        Returns:
            Loaded classifier component
        """
        try:
            with model_storage.read_from(resource) as model_dir:
                model_path = model_dir / "model.pkl"
                vectorizer_path = model_dir / "vectorizer.pkl"
                
                with open(model_path, "rb") as f:
                    model = pickle.load(f)
                with open(vectorizer_path, "rb") as f:
                    vectorizer = pickle.load(f)
                
                classifier = cls(
                    config=config,
                    model_storage=model_storage,
                    resource=resource,
                )
                classifier.clf = model
                classifier.vectorizer = vectorizer
                
                return classifier
        except Exception as e:
            print(f"Error loading model: {e}")
            return cls(config, model_storage, resource)