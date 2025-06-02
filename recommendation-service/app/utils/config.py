import yaml
import os
import re
from typing import Dict, Any, Optional
from functools import lru_cache
from pathlib import Path

class ConfigLoader:
    """YAML 설정 파일 로더 (백엔드 스타일)"""
    
    def __init__(self, config_dir: str = "/app/config"):
        self.config_dir = Path(config_dir)
        self._config_cache = {}
    
    def load_config(self, profile: str = "default") -> Dict[str, Any]:
        """설정 파일 로드 및 병합"""
        if profile in self._config_cache:
            return self._config_cache[profile]
        
        # 기본 설정 로드
        main_config = self._load_yaml_file("application.yml")
        
        # 프로필별 설정 로드 (있는 경우)
        if profile != "default":
            profile_config = self._load_yaml_file(f"application-{profile}.yml")
            main_config = self._merge_configs(main_config, profile_config)
        
        # 비밀 설정 로드
        secret_config = self._load_yaml_file("application-secret.yml")
        if secret_config:
            main_config = self._merge_configs(main_config, secret_config)
        
        # 환경변수 치환
        main_config = self._substitute_env_vars(main_config)
        
        self._config_cache[profile] = main_config
        return main_config
    
    def _load_yaml_file(self, filename: str) -> Dict[str, Any]:
        """YAML 파일 로드"""
        file_path = self.config_dir / filename
        
        if not file_path.exists():
            if "secret" in filename:
                print(f"⚠️ 비밀 설정 파일이 없습니다: {filename}")
                return {}
            else:
                raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {filename}")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise ValueError(f"YAML 파싱 오류 ({filename}): {e}")
    
    def _merge_configs(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """설정 딕셔너리 병합"""
        result = base.copy()
        
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value
        
        return result
    
    def _substitute_env_vars(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """환경변수 및 설정 참조 치환 (${key.path} 형식)"""
        def substitute_value(value, context=config):
            if isinstance(value, str):
                # ${key.path} 패턴 찾기
                pattern = r'\$\{([^}]+)\}'
                matches = re.findall(pattern, value)
                
                for match in matches:
                    # 점으로 구분된 키 경로 처리
                    keys = match.split('.')
                    replacement = context
                    
                    try:
                        for key in keys:
                            replacement = replacement[key]
                        
                        # 문자열로 변환하여 치환
                        value = value.replace(f'${{{match}}}', str(replacement))
                    except (KeyError, TypeError):
                        # 환경변수에서 찾기
                        env_value = os.getenv(match.replace('.', '_').upper())
                        if env_value:
                            value = value.replace(f'${{{match}}}', env_value)
                        else:
                            print(f"⚠️ 설정 참조를 찾을 수 없습니다: {match}")
                
                return value
            elif isinstance(value, dict):
                return {k: substitute_value(v, context) for k, v in value.items()}
            elif isinstance(value, list):
                return [substitute_value(item, context) for item in value]
            else:
                return value
        
        return substitute_value(config)

class Settings:
    """애플리케이션 설정 클래스"""
    
    def __init__(self, profile: str = None):
        # 프로필 결정 (환경변수 > 파라미터 > 기본값)
        self.profile = profile or os.getenv('SPRING_PROFILES_ACTIVE', 'default')
        
        # 설정 디렉토리 결정
        config_dir = os.getenv('CONFIG_DIR', '/app/config')
        if not os.path.exists(config_dir):
            # 개발 환경에서는 상대 경로 사용
            config_dir = os.path.join(os.path.dirname(__file__), '../../config')
        
        self.loader = ConfigLoader(config_dir)
        self.config = self.loader.load_config(self.profile)
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """점 표기법으로 설정값 조회 (예: 'datasource.host')"""
        keys = key_path.split('.')
        value = self.config
        
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default
    
    # 자주 사용하는 설정들을 프로퍼티로 제공
    @property
    def service_name(self) -> str:
        return self.get('service.name', 'recommendation-service')
    
    @property
    def service_version(self) -> str:
        return self.get('service.version', '1.0.0')
    
    @property
    def debug(self) -> bool:
        return self.get('service.debug', False)
    
    @property
    def server_host(self) -> str:
        return self.get('server.host', '0.0.0.0')
    
    @property
    def server_port(self) -> int:
        return self.get('server.port', 8000)
    
    @property
    def db_url(self) -> str:
        return self.get('datasource.url', '')
    
    @property
    def db_host(self) -> str:
        return self.get('datasource.host', 'localhost')
    
    @property
    def db_port(self) -> int:
        return self.get('datasource.port', 3306)
    
    @property
    def db_name(self) -> str:
        return self.get('datasource.database', 'travelonna')
    
    @property
    def db_user(self) -> str:
        return self.get('datasource.username', 'admin')
    
    @property
    def db_password(self) -> str:
        return self.get('datasource.password', '')
    
    @property
    def model_path(self) -> str:
        return self.get('model.path', '/app/models')
    
    @property
    def log_level(self) -> str:
        return self.get('logging.level', 'INFO')

@lru_cache()
def get_settings(profile: str = None) -> Settings:
    """설정 인스턴스 반환 (캐시됨)"""
    return Settings(profile)