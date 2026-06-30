import xml.etree.ElementTree as ET
import re
from typing import List, Optional, Dict, Any, TYPE_CHECKING

from .version_utils import _get_element_text

if TYPE_CHECKING:
    from .client import MavenClient


class PomParser:
    def __init__(self, client: "MavenClient"):
        self.client = client

    def _merge_poms(self, parent_pom: Dict, child_pom: Dict) -> Dict:
        merged: Dict[str, Any] = {
            "properties": {},
            "dependency_management": {},
            "dependencies": [],
            "repositories": [],
            "plugin_repositories": [],
            "plugins": [],
            "plugin_management": {},
            "profiles": {},
            "exclusions": {},
            "modules": [],
        }

        merged["properties"] = {
            **parent_pom.get("properties", {}),
            **child_pom.get("properties", {}),
        }

        merged["dependency_management"] = {
            **parent_pom.get("dependency_management", {}),
            **child_pom.get("dependency_management", {}),
        }

        parent_deps = {
            f"{d['group_id']}:{d['artifact_id']}": d
            for d in parent_pom.get("dependencies", [])
        }
        child_deps = {
            f"{d['group_id']}:{d['artifact_id']}": d
            for d in child_pom.get("dependencies", [])
        }

        for key, dep in parent_deps.items():
            merged_dep = dep.copy()
            if key in merged["dependency_management"]:
                merged_dep.update(merged["dependency_management"][key])
            merged["dependencies"].append(merged_dep)

        for key, dep in child_deps.items():
            if key not in parent_deps:
                merged["dependencies"].append(dep)
            else:
                for i, merged_dep in enumerate(merged["dependencies"]):
                    if f"{merged_dep['group_id']}:{merged_dep['artifact_id']}" == key:
                        merged["dependencies"][i] = dep
                        break

        repo_ids = set()
        for repo in parent_pom.get("repositories", []) + child_pom.get(
            "repositories", []
        ):
            if repo.get("id") not in repo_ids:
                merged["repositories"].append(repo)
                repo_ids.add(repo.get("id"))

        plugin_repo_ids = set()
        for repo in parent_pom.get("plugin_repositories", []) + child_pom.get(
            "plugin_repositories", []
        ):
            if repo.get("id") not in plugin_repo_ids:
                merged["plugin_repositories"].append(repo)
                plugin_repo_ids.add(repo.get("id"))

        merged["plugin_management"] = {
            **parent_pom.get("plugin_management", {}),
            **child_pom.get("plugin_management", {}),
        }

        parent_plugins = {
            f"{p['group_id']}:{p['artifact_id']}": p
            for p in parent_pom.get("plugins", [])
        }
        child_plugins = {
            f"{p['group_id']}:{p['artifact_id']}": p
            for p in child_pom.get("plugins", [])
        }

        for key, plugin in parent_plugins.items():
            merged["plugins"].append(plugin)

        for key, plugin in child_plugins.items():
            if key not in parent_plugins:
                merged["plugins"].append(plugin)
            else:
                for i, merged_plugin in enumerate(merged["plugins"]):
                    if (
                        f"{merged_plugin['group_id']}:{merged_plugin['artifact_id']}"
                        == key
                    ):
                        merged["plugins"][i] = plugin
                        break

        merged["profiles"] = {
            **parent_pom.get("profiles", {}),
            **child_pom.get("profiles", {}),
        }
        merged["modules"] = child_pom.get("modules", [])

        for key in child_pom:
            if key not in merged:
                merged[key] = child_pom[key]

        return merged

    def _extract_properties(self, root, namespaces) -> Dict[str, str]:
        properties: Dict[str, str] = {}
        props_elem = root.find(".//maven:properties", namespaces) or root.find(
            ".//properties"
        )

        if props_elem is not None:
            for prop in props_elem:
                tag = prop.tag.split("}")[-1] if "}" in prop.tag else prop.tag
                if prop.text:
                    properties[tag] = prop.text.strip()

        return properties

    def _substitute_properties(self, value: str, properties: Dict[str, str]) -> str:
        if not value or "${" not in value:
            return value

        pattern = re.compile(r"\$\{([^}]+)\}")

        def replace_property(match):
            prop_name = match.group(1)
            if prop_name in properties:
                return self._substitute_properties(properties[prop_name], properties)
            return match.group(0)

        max_iterations = 10
        for _ in range(max_iterations):
            new_value = pattern.sub(replace_property, value)
            if new_value == value:
                break
            value = new_value

        return value

    def _extract_parent_info(self, parent_elem, namespaces) -> Optional[Dict]:
        try:
            group_id = _get_element_text(parent_elem, "groupId", namespaces)
            artifact_id = _get_element_text(parent_elem, "artifactId", namespaces)
            version = _get_element_text(parent_elem, "version", namespaces)

            if group_id and artifact_id:
                return {
                    "name": f"{group_id}:{artifact_id}",
                    "group_id": group_id,
                    "artifact_id": artifact_id,
                    "version": version or "unspecified",
                    "scope": "parent",
                    "optional": False,
                    "type": "parent",
                }
        except Exception:
            pass
        return None

    def _parse_repositories(self, root, namespaces, properties) -> List[Dict]:
        repositories: List[Dict] = []

        repos_elem = root.find(".//maven:repositories", namespaces) or root.find(
            ".//repositories"
        )
        if repos_elem is not None:
            for repo in repos_elem.findall(
                ".//maven:repository", namespaces
            ) or repos_elem.findall(".//repository"):
                repo_info: Dict[str, Any] = {
                    "id": self._substitute_properties(
                        _get_element_text(repo, "id", namespaces) or "", properties
                    ),
                    "url": self._substitute_properties(
                        _get_element_text(repo, "url", namespaces) or "",
                        properties,
                    ),
                    "layout": _get_element_text(repo, "layout", namespaces)
                    or "default",
                }

                releases_elem = repo.find(".//maven:releases", namespaces) or repo.find(
                    ".//releases"
                )
                if releases_elem is not None:
                    repo_info["releases"] = {
                        "enabled": _get_element_text(
                            releases_elem, "enabled", namespaces
                        )
                        != "false",
                        "updatePolicy": _get_element_text(
                            releases_elem, "updatePolicy", namespaces
                        )
                        or "daily",
                        "checksumPolicy": _get_element_text(
                            releases_elem, "checksumPolicy", namespaces
                        )
                        or "warn",
                    }

                snapshots_elem = repo.find(
                    ".//maven:snapshots", namespaces
                ) or repo.find(".//snapshots")
                if snapshots_elem is not None:
                    repo_info["snapshots"] = {
                        "enabled": _get_element_text(
                            snapshots_elem, "enabled", namespaces
                        )
                        == "true",
                        "updatePolicy": _get_element_text(
                            snapshots_elem, "updatePolicy", namespaces
                        )
                        or "daily",
                        "checksumPolicy": _get_element_text(
                            snapshots_elem, "checksumPolicy", namespaces
                        )
                        or "warn",
                    }

                repositories.append(repo_info)

        return repositories

    def _parse_plugin_repositories(self, root, namespaces, properties) -> List[Dict]:
        repositories: List[Dict] = []

        repos_elem = root.find(".//maven:pluginRepositories", namespaces) or root.find(
            ".//pluginRepositories"
        )
        if repos_elem is not None:
            for repo in repos_elem.findall(
                ".//maven:pluginRepository", namespaces
            ) or repos_elem.findall(".//pluginRepository"):
                repo_info: Dict[str, Any] = {
                    "id": self._substitute_properties(
                        _get_element_text(repo, "id", namespaces) or "", properties
                    ),
                    "url": self._substitute_properties(
                        _get_element_text(repo, "url", namespaces) or "",
                        properties,
                    ),
                    "layout": _get_element_text(repo, "layout", namespaces)
                    or "default",
                }
                repositories.append(repo_info)

        return repositories

    def _parse_dependency_management(
        self, dep_mgmt_elem, namespaces, properties
    ) -> Dict[str, Dict]:
        dep_management: Dict[str, Dict] = {}

        deps_elem = dep_mgmt_elem.find(
            ".//maven:dependencies", namespaces
        ) or dep_mgmt_elem.find(".//dependencies")
        if deps_elem is not None:
            for dep in deps_elem.findall(
                ".//maven:dependency", namespaces
            ) or deps_elem.findall(".//dependency"):
                dep_info = self._extract_dependency_info(
                    dep, namespaces, properties, {}
                )
                if dep_info:
                    key = f"{dep_info['group_id']}:{dep_info['artifact_id']}"
                    dep_management[key] = dep_info

        return dep_management

    def _parse_plugin_management(
        self, plugin_mgmt_elem, namespaces, properties
    ) -> Dict[str, Dict]:
        plugin_management: Dict[str, Dict] = {}

        plugins_elem = plugin_mgmt_elem.find(
            ".//maven:plugins", namespaces
        ) or plugin_mgmt_elem.find(".//plugins")
        if plugins_elem is not None:
            for plugin in plugins_elem.findall(
                ".//maven:plugin", namespaces
            ) or plugins_elem.findall(".//plugin"):
                plugin_info = self._extract_plugin_info(
                    plugin, namespaces, properties, {}
                )
                if plugin_info:
                    key = f"{plugin_info['group_id']}:{plugin_info['artifact_id']}"
                    plugin_management[key] = plugin_info

        return plugin_management

    def _parse_profiles(
        self, profiles_elem, namespaces, parent_properties
    ) -> Dict[str, Dict]:
        profiles: Dict[str, Dict] = {}

        for profile in profiles_elem.findall(
            ".//maven:profile", namespaces
        ) or profiles_elem.findall(".//profile"):
            profile_id = _get_element_text(profile, "id", namespaces)
            if not profile_id:
                continue

            profile_data: Dict[str, Any] = {
                "id": profile_id,
                "properties": {},
                "dependencies": [],
                "dependency_management": {},
                "activeByDefault": False,
                "activation": {},
            }

            activation_elem = profile.find(
                ".//maven:activation", namespaces
            ) or profile.find(".//activation")
            if activation_elem is not None:
                active_by_default = _get_element_text(
                    activation_elem, "activeByDefault", namespaces
                )
                profile_data["activeByDefault"] = active_by_default == "true"
                profile_data["activation"] = self._parse_activation(
                    activation_elem, namespaces
                )

            props_elem = profile.find(
                ".//maven:properties", namespaces
            ) or profile.find(".//properties")
            if props_elem is not None:
                profile_props = self._extract_properties(profile, namespaces)
                all_props = {**parent_properties, **profile_props}
                for key, value in profile_props.items():
                    profile_data["properties"][key] = self._substitute_properties(
                        value, all_props
                    )

            deps_elem = profile.find(
                ".//maven:dependencies", namespaces
            ) or profile.find(".//dependencies")
            if deps_elem is not None:
                all_props = {**parent_properties, **profile_data["properties"]}
                profile_data["dependencies"] = self._parse_dependencies_section(
                    deps_elem, namespaces, all_props, {}
                )

            dep_mgmt_elem = profile.find(
                ".//maven:dependencyManagement", namespaces
            ) or profile.find(".//dependencyManagement")
            if dep_mgmt_elem is not None:
                all_props = {**parent_properties, **profile_data["properties"]}
                profile_data["dependency_management"] = (
                    self._parse_dependency_management(
                        dep_mgmt_elem, namespaces, all_props
                    )
                )

            profiles[profile_id] = profile_data

        return profiles

    def _parse_activation(self, activation_elem, namespaces) -> Dict:
        activation: Dict[str, Any] = {}

        jdk = _get_element_text(activation_elem, "jdk", namespaces)
        if jdk:
            activation["jdk"] = jdk

        os_elem = activation_elem.find(
            ".//maven:os", namespaces
        ) or activation_elem.find(".//os")
        if os_elem is not None:
            activation["os"] = {
                "name": _get_element_text(os_elem, "name", namespaces),
                "family": _get_element_text(os_elem, "family", namespaces),
                "arch": _get_element_text(os_elem, "arch", namespaces),
                "version": _get_element_text(os_elem, "version", namespaces),
            }

        prop_elem = activation_elem.find(
            ".//maven:property", namespaces
        ) or activation_elem.find(".//property")
        if prop_elem is not None:
            activation["property"] = {
                "name": _get_element_text(prop_elem, "name", namespaces),
                "value": _get_element_text(prop_elem, "value", namespaces),
            }

        return activation

    def _parse_dependencies_section(
        self, deps_elem, namespaces, properties, dep_management
    ) -> List[Dict]:
        dependencies: List[Dict] = []
        for dep in deps_elem.findall(
            ".//maven:dependency", namespaces
        ) or deps_elem.findall(".//dependency"):
            dep_info = self._extract_dependency_info_with_exclusions(
                dep, namespaces, properties, dep_management
            )
            if dep_info:
                dependencies.append(dep_info)

        return dependencies

    def _extract_dependency_info(
        self, dep_elem, namespaces, properties, dep_management
    ) -> Optional[Dict]:
        try:
            group_id = _get_element_text(dep_elem, "groupId", namespaces)
            artifact_id = _get_element_text(dep_elem, "artifactId", namespaces)
            version = _get_element_text(dep_elem, "version", namespaces)
            scope = _get_element_text(dep_elem, "scope", namespaces) or "compile"
            optional = _get_element_text(dep_elem, "optional", namespaces) == "true"
            dep_type = _get_element_text(dep_elem, "type", namespaces) or "jar"
            classifier = _get_element_text(dep_elem, "classifier", namespaces)

            group_id = (
                self._substitute_properties(group_id, properties) if group_id else None
            )
            artifact_id = (
                self._substitute_properties(artifact_id, properties)
                if artifact_id
                else None
            )
            version = (
                self._substitute_properties(version, properties) if version else None
            )

            if group_id and artifact_id:
                group_id, artifact_id = self.client._normalize_maven_coordinates(
                    group_id, artifact_id
                )

            if group_id and artifact_id:
                dep_key = f"{group_id}:{artifact_id}"
                if dep_key in dep_management and not version:
                    managed_dep = dep_management[dep_key]
                    version = managed_dep.get("version", version)
                    scope = scope or managed_dep.get("scope", "compile")

                version_info = (
                    self.client._parse_version_range(version) if version else None
                )

                return {
                    "name": f"{group_id}:{artifact_id}",
                    "group_id": group_id,
                    "artifact_id": artifact_id,
                    "version": version or "unspecified",
                    "version_range": version_info,
                    "scope": scope,
                    "optional": optional,
                    "type": "dependency",
                    "classifier": classifier,
                    "packaging": dep_type,
                }
        except Exception as e:
            print(f"Error extracting dependency: {str(e)}")
        return None

    def _extract_dependency_info_with_exclusions(
        self, dep_elem, namespaces, properties, dep_management
    ) -> Optional[Dict]:
        dep_info = self._extract_dependency_info(
            dep_elem, namespaces, properties, dep_management
        )

        if dep_info:
            exclusions = []
            exclusions_elem = dep_elem.find(
                ".//maven:exclusions", namespaces
            ) or dep_elem.find(".//exclusions")

            if exclusions_elem is not None:
                for exclusion in exclusions_elem.findall(
                    ".//maven:exclusion", namespaces
                ) or exclusions_elem.findall(".//exclusion"):
                    exc_group_id = _get_element_text(exclusion, "groupId", namespaces)
                    exc_artifact_id = _get_element_text(
                        exclusion, "artifactId", namespaces
                    )

                    if exc_group_id or exc_artifact_id:
                        exclusions.append(
                            {
                                "group_id": self._substitute_properties(
                                    exc_group_id, properties
                                )
                                if exc_group_id
                                else "*",
                                "artifact_id": self._substitute_properties(
                                    exc_artifact_id, properties
                                )
                                if exc_artifact_id
                                else "*",
                            }
                        )

            if exclusions:
                dep_info["exclusions"] = exclusions

        return dep_info

    def _parse_plugins_section(
        self, plugins_elem, namespaces, properties, plugin_management
    ) -> List[Dict]:
        plugins = []

        for plugin in plugins_elem.findall(
            ".//maven:plugin", namespaces
        ) or plugins_elem.findall(".//plugin"):
            plugin_info = self._extract_plugin_info(
                plugin, namespaces, properties, plugin_management
            )
            if plugin_info:
                plugins.append(plugin_info)

        return plugins

    def _extract_plugin_info(
        self, plugin_elem, namespaces, properties, plugin_management
    ) -> Optional[Dict]:
        try:
            group_id = (
                _get_element_text(plugin_elem, "groupId", namespaces)
                or "org.apache.maven.plugins"
            )
            artifact_id = _get_element_text(plugin_elem, "artifactId", namespaces)
            version = _get_element_text(plugin_elem, "version", namespaces)

            group_id = self._substitute_properties(group_id, properties)
            artifact_id = (
                self._substitute_properties(artifact_id, properties)
                if artifact_id
                else None
            )
            version = (
                self._substitute_properties(version, properties) if version else None
            )

            if group_id and artifact_id:
                plugin_key = f"{group_id}:{artifact_id}"
                if plugin_key in plugin_management and not version:
                    managed_plugin = plugin_management[plugin_key]
                    version = managed_plugin.get("version", version)

                plugin_info: Dict[str, Any] = {
                    "name": f"{group_id}:{artifact_id}",
                    "group_id": group_id,
                    "artifact_id": artifact_id,
                    "version": version or "unspecified",
                    "type": "plugin",
                    "dependencies": [],
                }

                deps_elem = plugin_elem.find(
                    ".//maven:dependencies", namespaces
                ) or plugin_elem.find(".//dependencies")
                if deps_elem is not None:
                    plugin_info["dependencies"] = self._parse_dependencies_section(
                        deps_elem, namespaces, properties, {}
                    )

                config_elem = plugin_elem.find(
                    ".//maven:configuration", namespaces
                ) or plugin_elem.find(".//configuration")
                if config_elem is not None:
                    plugin_info["configuration"] = self._parse_configuration(
                        config_elem, properties
                    )

                executions = []
                for exec_elem in plugin_elem.findall(
                    ".//maven:execution", namespaces
                ) or plugin_elem.findall(".//execution"):
                    execution = {
                        "id": _get_element_text(exec_elem, "id", namespaces)
                        or "default",
                        "phase": _get_element_text(exec_elem, "phase", namespaces),
                        "goals": [
                            g.text.strip()
                            for g in (
                                exec_elem.findall(".//maven:goal", namespaces)
                                or exec_elem.findall(".//goal")
                            )
                            if g.text
                        ],
                    }
                    executions.append(execution)

                if executions:
                    plugin_info["executions"] = executions

                return plugin_info

        except Exception as e:
            print(f"Error extracting plugin: {str(e)}")
        return None

    def _parse_configuration(self, config_elem, properties) -> Dict:
        config: Dict[str, Any] = {}

        for child in config_elem:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if len(child) == 0:
                if child.text:
                    config[tag] = self._substitute_properties(
                        child.text.strip(), properties
                    )
            else:
                config[tag] = self._parse_configuration(child, properties)

        return config

    def _parse_pom_comprehensive(
        self,
        pom_xml: str,
        group_id: str,
        artifact_id: str,
        version: str,
        active_profiles: Optional[List[str]] = None,
    ) -> Dict:
        try:
            root = ET.fromstring(pom_xml)
            namespaces = {"maven": "http://maven.apache.org/POM/4.0.0"}

            pom_data: Dict[str, Any] = {
                "properties": {},
                "dependency_management": {},
                "dependencies": [],
                "repositories": [],
                "plugin_repositories": [],
                "plugins": [],
                "plugin_management": {},
                "profiles": {},
                "parent": None,
                "modules": [],
            }

            pom_data["properties"] = self._extract_properties(root, namespaces)

            pom_data["properties"].update(
                {
                    "project.groupId": group_id,
                    "project.artifactId": artifact_id,
                    "project.version": version,
                    "project.packaging": _get_element_text(
                        root, "packaging", namespaces
                    )
                    or "jar",
                    "pom.groupId": group_id,
                    "pom.artifactId": artifact_id,
                    "pom.version": version,
                }
            )

            parent_elem = root.find(".//maven:parent", namespaces) or root.find(
                ".//parent"
            )
            if parent_elem is not None:
                pom_data["parent"] = self._extract_parent_info(parent_elem, namespaces)

            pom_data["repositories"] = self._parse_repositories(
                root, namespaces, pom_data["properties"]
            )
            pom_data["plugin_repositories"] = self._parse_plugin_repositories(
                root, namespaces, pom_data["properties"]
            )

            dep_mgmt_elem = root.find(
                ".//maven:dependencyManagement", namespaces
            ) or root.find(".//dependencyManagement")
            if dep_mgmt_elem is not None:
                pom_data["dependency_management"] = self._parse_dependency_management(
                    dep_mgmt_elem, namespaces, pom_data["properties"]
                )

            plugin_mgmt_elem = root.find(
                ".//maven:build/maven:pluginManagement", namespaces
            ) or root.find(".//build/pluginManagement")
            if plugin_mgmt_elem is not None:
                pom_data["plugin_management"] = self._parse_plugin_management(
                    plugin_mgmt_elem, namespaces, pom_data["properties"]
                )

            profiles_elem = root.find(".//maven:profiles", namespaces) or root.find(
                ".//profiles"
            )
            if profiles_elem is not None:
                pom_data["profiles"] = self._parse_profiles(
                    profiles_elem, namespaces, pom_data["properties"]
                )

            deps_elem = root.find(".//maven:dependencies", namespaces) or root.find(
                ".//dependencies"
            )
            if deps_elem is not None:
                main_deps = self._parse_dependencies_section(
                    deps_elem,
                    namespaces,
                    pom_data["properties"],
                    pom_data["dependency_management"],
                )
                pom_data["dependencies"].extend(main_deps)

            plugins_elem = root.find(
                ".//maven:build/maven:plugins", namespaces
            ) or root.find(".//build/plugins")
            if plugins_elem is not None:
                pom_data["plugins"] = self._parse_plugins_section(
                    plugins_elem,
                    namespaces,
                    pom_data["properties"],
                    pom_data["plugin_management"],
                )

            modules = root.findall(".//maven:module", namespaces) or root.findall(
                ".//module"
            )
            pom_data["modules"] = [
                self._substitute_properties(m.text.strip(), pom_data["properties"])
                for m in modules
                if m.text
            ]

            if active_profiles:
                pom_data = self._apply_profiles(pom_data, active_profiles)

            pom_data = self._apply_default_profiles(pom_data, active_profiles)

            return pom_data

        except ET.ParseError as e:
            print(f"XML Parse error: {str(e)}")
            return {"dependencies": []}

    def _apply_profiles(self, pom_data: Dict, active_profiles: List[str]) -> Dict:
        for profile_id in active_profiles:
            if profile_id in pom_data.get("profiles", {}):
                profile = pom_data["profiles"][profile_id]

                pom_data["properties"].update(profile.get("properties", {}))

                pom_data["dependencies"].extend(profile.get("dependencies", []))

                if "dependency_management" in profile:
                    pom_data["dependency_management"].update(
                        profile["dependency_management"]
                    )

                pom_data["repositories"].extend(profile.get("repositories", []))

                pom_data["plugins"].extend(profile.get("plugins", []))

                if "plugin_management" in profile:
                    pom_data["plugin_management"].update(profile["plugin_management"])

        return pom_data

    def _apply_default_profiles(
        self, pom_data: Dict, active_profiles: Optional[List[str]]
    ) -> Dict:
        if active_profiles:
            return pom_data

        for profile_id, profile in pom_data.get("profiles", {}).items():
            if profile.get("activeByDefault", False):
                pom_data["properties"].update(profile.get("properties", {}))
                pom_data["dependencies"].extend(profile.get("dependencies", []))
                if "dependency_management" in profile:
                    pom_data["dependency_management"].update(
                        profile["dependency_management"]
                    )
                pom_data["repositories"].extend(profile.get("repositories", []))
                pom_data["plugins"].extend(profile.get("plugins", []))
                if "plugin_management" in profile:
                    pom_data["plugin_management"].update(profile["plugin_management"])

        return pom_data

    def _apply_final_property_substitution(self, pom_data: Dict) -> Dict:
        for dep in pom_data.get("dependencies", []):
            for key in ["group_id", "artifact_id", "version"]:
                if key in dep and dep[key]:
                    dep[key] = self._substitute_properties(
                        dep[key], pom_data["properties"]
                    )

        for plugin in pom_data.get("plugins", []):
            for key in ["group_id", "artifact_id", "version"]:
                if key in plugin and plugin[key]:
                    plugin[key] = self._substitute_properties(
                        plugin[key], pom_data["properties"]
                    )

        return pom_data
