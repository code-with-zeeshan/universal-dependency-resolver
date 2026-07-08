"""Tests for Maven POM parser deep XML parsing."""

import xml.etree.ElementTree as ET
from unittest.mock import MagicMock

import pytest

from backend.data_sources.maven.pom_parser import PomParser


@pytest.fixture
def parser():
    client = MagicMock()
    client._normalize_maven_coordinates.side_effect = lambda g, a: (g, a)
    client._parse_version_range.return_value = None
    return PomParser(client)


NAMESPACES = {"maven": "http://maven.apache.org/POM/4.0.0"}


def _pom_xml(body: str) -> ET.Element:
    return ET.fromstring(f'<project xmlns="http://maven.apache.org/POM/4.0.0">{body}</project>')


class TestParseRepositories:
    def test_no_repositories(self, parser):
        root = _pom_xml("")
        assert parser._parse_repositories(root, NAMESPACES, {}) == []

    def test_single_repository(self, parser):
        root = _pom_xml("""
            <repositories>
                <repository>
                    <id>central</id>
                    <url>https://repo.maven.apache.org/maven2</url>
                </repository>
            </repositories>
        """)
        repos = parser._parse_repositories(root, NAMESPACES, {})
        assert len(repos) == 1
        assert repos[0]["id"] == "central"
        assert repos[0]["url"] == "https://repo.maven.apache.org/maven2"
        assert repos[0]["layout"] == "default"

    def test_repository_with_releases(self, parser):
        root = _pom_xml("""
            <repositories>
                <repository>
                    <id>custom</id>
                    <url>https://custom.repo</url>
                    <releases>
                        <enabled>true</enabled>
                        <updatePolicy>always</updatePolicy>
                    </releases>
                </repository>
            </repositories>
        """)
        repos = parser._parse_repositories(root, NAMESPACES, {})
        assert repos[0]["releases"]["enabled"] is True
        assert repos[0]["releases"]["updatePolicy"] == "always"

    def test_repository_with_snapshots(self, parser):
        root = _pom_xml("""
            <repositories>
                <repository>
                    <id>snapshots</id>
                    <url>https://snapshots.repo</url>
                    <snapshots>
                        <enabled>true</enabled>
                        <updatePolicy>daily</updatePolicy>
                    </snapshots>
                </repository>
            </repositories>
        """)
        repos = parser._parse_repositories(root, NAMESPACES, {})
        assert repos[0]["snapshots"]["enabled"] is True

    def test_property_substitution_in_repo(self, parser):
        root = _pom_xml("""
            <repositories>
                <repository>
                    <id>${repo.id}</id>
                    <url>${repo.url}</url>
                </repository>
            </repositories>
        """)
        repos = parser._parse_repositories(
            root, NAMESPACES, {"repo.id": "myrepo", "repo.url": "https://my.repo"}
        )
        assert repos[0]["id"] == "myrepo"
        assert repos[0]["url"] == "https://my.repo"


class TestParsePluginRepositories:
    def test_no_plugin_repositories(self, parser):
        root = _pom_xml("")
        assert parser._parse_plugin_repositories(root, NAMESPACES, {}) == []

    def test_single_plugin_repository(self, parser):
        root = _pom_xml("""
            <pluginRepositories>
                <pluginRepository>
                    <id>plugin-central</id>
                    <url>https://plugins.repo</url>
                </pluginRepository>
            </pluginRepositories>
        """)
        repos = parser._parse_plugin_repositories(root, NAMESPACES, {})
        assert len(repos) == 1
        assert repos[0]["id"] == "plugin-central"


class TestParseDependencyManagement:
    def test_empty_dependency_management(self, parser):
        root = _pom_xml("<dependencyManagement/>")
        result = parser._parse_dependency_management(root, NAMESPACES, {})
        assert result == {}

    def test_single_dependency_management(self, parser):
        root = _pom_xml("""
            <dependencyManagement>
                <dependencies>
                    <dependency>
                        <groupId>com.google.guava</groupId>
                        <artifactId>guava</artifactId>
                        <version>32.1.3-jre</version>
                    </dependency>
                </dependencies>
            </dependencyManagement>
        """)
        result = parser._parse_dependency_management(root, NAMESPACES, {})
        assert "com.google.guava:guava" in result
        assert result["com.google.guava:guava"]["version"] == "32.1.3-jre"

    def test_dependency_management_with_exclusions(self, parser):
        root = _pom_xml("""
            <dependencyManagement>
                <dependencies>
                    <dependency>
                        <groupId>org.example</groupId>
                        <artifactId>lib</artifactId>
                        <version>1.0</version>
                        <exclusions>
                            <exclusion>
                                <groupId>org.unwanted</groupId>
                                <artifactId>bad</artifactId>
                            </exclusion>
                        </exclusions>
                    </dependency>
                </dependencies>
            </dependencyManagement>
        """)
        result = parser._parse_dependency_management(root, NAMESPACES, {})
        assert "org.example:lib" in result
        assert result["org.example:lib"]["version"] == "1.0"

    def test_dependency_management_scope(self, parser):
        root = _pom_xml("""
            <dependencyManagement>
                <dependencies>
                    <dependency>
                        <groupId>org.test</groupId>
                        <artifactId>test-lib</artifactId>
                        <version>2.0</version>
                        <scope>import</scope>
                        <type>pom</type>
                    </dependency>
                </dependencies>
            </dependencyManagement>
        """)
        result = parser._parse_dependency_management(root, NAMESPACES, {})
        assert result["org.test:test-lib"]["scope"] == "import"
        assert result["org.test:test-lib"]["packaging"] == "pom"


class TestParsePluginManagement:
    def test_empty_plugin_management(self, parser):
        root = _pom_xml("<pluginManagement/>")
        result = parser._parse_plugin_management(root, NAMESPACES, {})
        assert result == {}

    def test_single_plugin_management(self, parser):
        root = _pom_xml("""
            <build>
                <pluginManagement>
                    <plugins>
                        <plugin>
                            <groupId>org.apache.maven.plugins</groupId>
                            <artifactId>maven-compiler-plugin</artifactId>
                            <version>3.8.1</version>
                        </plugin>
                    </plugins>
                </pluginManagement>
            </build>
        """)
        result = parser._parse_plugin_management(root, NAMESPACES, {})
        key = "org.apache.maven.plugins:maven-compiler-plugin"
        assert key in result
        assert result[key]["version"] == "3.8.1"


class TestParseProfiles:
    def test_no_profiles(self, parser):
        root = _pom_xml("")
        assert parser._parse_profiles(root, NAMESPACES, {}) == {}

    def test_single_profile(self, parser):
        root = _pom_xml("""
            <profiles>
                <profile>
                    <id>java11</id>
                    <properties>
                        <java.version>11</java.version>
                    </properties>
                </profile>
            </profiles>
        """)
        profiles = parser._parse_profiles(root, NAMESPACES, {})
        assert "java11" in profiles
        assert profiles["java11"]["properties"]["java.version"] == "11"

    def test_profile_with_activation(self, parser):
        root = _pom_xml("""
            <profiles>
                <profile>
                    <id>jdk11</id>
                    <activation>
                        <jdk>11</jdk>
                    </activation>
                </profile>
            </profiles>
        """)
        profiles = parser._parse_profiles(root, NAMESPACES, {})
        assert profiles["jdk11"]["activation"]["jdk"] == "11"

    def test_profile_with_dependencies(self, parser):
        root = _pom_xml("""
            <profiles>
                <profile>
                    <id>extra</id>
                    <dependencies>
                        <dependency>
                            <groupId>org.extra</groupId>
                            <artifactId>extra-lib</artifactId>
                            <version>1.0</version>
                        </dependency>
                    </dependencies>
                </profile>
            </profiles>
        """)
        profiles = parser._parse_profiles(root, NAMESPACES, {})
        assert len(profiles["extra"]["dependencies"]) == 1


class TestParseActivation:
    def test_activation_by_jdk(self, parser):
        root = _pom_xml("""
            <profiles>
                <profile>
                    <id>test</id>
                    <activation>
                        <jdk>1.8</jdk>
                    </activation>
                </profile>
            </profiles>
        """)
        profiles = parser._parse_profiles(root, NAMESPACES, {})
        assert profiles["test"]["activation"]["jdk"] == "1.8"

    def test_activation_by_os(self, parser):
        root = _pom_xml("""
            <profiles>
                <profile>
                    <id>os-profile</id>
                    <activation>
                        <os>
                            <name>Linux</name>
                            <arch>amd64</arch>
                        </os>
                    </activation>
                </profile>
            </profiles>
        """)
        profiles = parser._parse_profiles(root, NAMESPACES, {})
        act = profiles["os-profile"]["activation"]
        assert act["os"]["name"] == "Linux"
        assert act["os"]["arch"] == "amd64"

    def test_activation_by_property(self, parser):
        root = _pom_xml("""
            <profiles>
                <profile>
                    <id>prop-profile</id>
                    <activation>
                        <property>
                            <name>env.DEBUG</name>
                            <value>true</value>
                        </property>
                    </activation>
                </profile>
            </profiles>
        """)
        profiles = parser._parse_profiles(root, NAMESPACES, {})
        assert profiles["prop-profile"]["activation"]["property"]["name"] == "env.DEBUG"

    def test_activation_active_by_default(self, parser):
        root = _pom_xml("""
            <profiles>
                <profile>
                    <id>default-profile</id>
                    <activation>
                        <activeByDefault>true</activeByDefault>
                    </activation>
                </profile>
            </profiles>
        """)
        profiles = parser._parse_profiles(root, NAMESPACES, {})
        assert profiles["default-profile"]["activeByDefault"] is True


class TestParsePlugins:
    def test_no_plugins(self, parser):
        root = _pom_xml("")
        assert parser._parse_plugins_section(root, NAMESPACES, {}, {}) == []

    def test_single_plugin(self, parser):
        root = _pom_xml("""
            <build>
                <plugins>
                    <plugin>
                        <groupId>org.apache.maven.plugins</groupId>
                        <artifactId>maven-compiler-plugin</artifactId>
                        <version>3.8.1</version>
                    </plugin>
                </plugins>
            </build>
        """)
        plugins = parser._parse_plugins_section(root, NAMESPACES, {}, {})
        assert len(plugins) == 1
        assert plugins[0]["artifact_id"] == "maven-compiler-plugin"

    def test_plugin_with_configuration(self, parser):
        root = _pom_xml("""
            <build>
                <plugins>
                    <plugin>
                        <groupId>org.apache.maven.plugins</groupId>
                        <artifactId>maven-surefire-plugin</artifactId>
                        <version>3.0.0</version>
                        <configuration>
                            <forkCount>2</forkCount>
                            <reuseForks>true</reuseForks>
                        </configuration>
                    </plugin>
                </plugins>
            </build>
        """)
        plugins = parser._parse_plugins_section(root, NAMESPACES, {}, {})
        assert plugins[0]["configuration"]["forkCount"] == "2"

    def test_plugin_with_executions(self, parser):
        root = _pom_xml("""
            <build>
                <plugins>
                    <plugin>
                        <groupId>org.codehaus.mojo</groupId>
                        <artifactId>exec-maven-plugin</artifactId>
                        <version>3.1.0</version>
                        <executions>
                            <execution>
                                <id>default-cli</id>
                                <phase>compile</phase>
                                <goals><goal>java</goal></goals>
                            </execution>
                        </executions>
                    </plugin>
                </plugins>
            </build>
        """)
        plugins = parser._parse_plugins_section(root, NAMESPACES, {}, {})
        assert len(plugins[0]["executions"]) == 1
        assert plugins[0]["executions"][0]["goals"] == ["java"]


class TestExtractDependencyInfo:
    def test_with_exclusions(self, parser):
        xml = """
            <dependency>
                <groupId>com.example</groupId>
                <artifactId>core</artifactId>
                <version>2.0</version>
                <exclusions>
                    <exclusion>
                        <groupId>com.unwanted</groupId>
                        <artifactId>bad-lib</artifactId>
                    </exclusion>
                </exclusions>
            </dependency>
        """
        dep_elem = ET.fromstring(xml)
        info = parser._extract_dependency_info_with_exclusions(dep_elem, NAMESPACES, {}, {})
        assert info["group_id"] == "com.example"
        assert info["artifact_id"] == "core"
        assert info["version"] == "2.0"
        assert info["exclusions"] == [{"group_id": "com.unwanted", "artifact_id": "bad-lib"}]

    def test_without_exclusions(self, parser):
        xml = """
            <dependency>
                <groupId>com.example</groupId>
                <artifactId>simple</artifactId>
                <version>1.0</version>
            </dependency>
        """
        dep_elem = ET.fromstring(xml)
        info = parser._extract_dependency_info_with_exclusions(dep_elem, NAMESPACES, {}, {})
        assert info["group_id"] == "com.example"
        assert "exclusions" not in info or info["exclusions"] == []

    def test_with_optional_flag(self, parser):
        xml = """
            <dependency>
                <groupId>com.example</groupId>
                <artifactId>optional-dep</artifactId>
                <version>1.0</version>
                <optional>true</optional>
            </dependency>
        """
        dep_elem = ET.fromstring(xml)
        info = parser._extract_dependency_info(dep_elem, NAMESPACES, {}, {})
        assert info["optional"] is True

    def test_dependency_with_type_and_scope(self, parser):
        xml = """
            <dependency>
                <groupId>org.test</groupId>
                <artifactId>test-lib</artifactId>
                <version>1.0</version>
                <type>war</type>
                <scope>runtime</scope>
            </dependency>
        """
        dep_elem = ET.fromstring(xml)
        info = parser._extract_dependency_info(dep_elem, NAMESPACES, {}, {})
        assert info["packaging"] == "war"
        assert info["scope"] == "runtime"


class TestApplyDefaultProfiles:
    def test_no_profiles(self, parser):
        pom_data = {"profiles": {}, "properties": {}, "dependencies": []}
        result = parser._apply_default_profiles(pom_data, None)
        assert result == pom_data

    def test_active_by_default_applied(self, parser):
        pom_data = {
            "profiles": {
                "default-profile": {
                    "activeByDefault": True,
                    "properties": {"java.version": "11"},
                    "dependencies": [],
                    "dependency_management": {},
                    "repositories": [],
                    "plugins": [],
                    "plugin_management": {},
                }
            },
            "properties": {},
            "dependencies": [],
            "dependency_management": {},
            "repositories": [],
            "plugins": [],
            "plugin_management": {},
        }
        result = parser._apply_default_profiles(pom_data, None)
        assert result["properties"]["java.version"] == "11"

    def test_non_active_profile_not_applied(self, parser):
        pom_data = {
            "profiles": {
                "non-default": {
                    "activeByDefault": False,
                    "properties": {"debug": "true"},
                    "dependencies": [],
                    "dependency_management": {},
                    "repositories": [],
                    "plugins": [],
                    "plugin_management": {},
                }
            },
            "properties": {},
            "dependencies": [],
            "dependency_management": {},
            "repositories": [],
            "plugins": [],
            "plugin_management": {},
        }
        result = parser._apply_default_profiles(pom_data, None)
        assert "debug" not in result.get("properties", {})

    def test_active_by_default_skipped_when_other_active(self, parser):
        pom_data = {
            "profiles": {
                "explicit": {
                    "properties": {"explicit": "true"},
                    "dependencies": [],
                    "dependency_management": {},
                    "repositories": [],
                    "plugins": [],
                    "plugin_management": {},
                },
                "default": {
                    "activeByDefault": True,
                    "properties": {"default": "true"},
                    "dependencies": [],
                    "dependency_management": {},
                    "repositories": [],
                    "plugins": [],
                    "plugin_management": {},
                },
            },
            "properties": {},
            "dependencies": [],
            "dependency_management": {},
            "repositories": [],
            "plugins": [],
            "plugin_management": {},
        }
        result = parser._apply_default_profiles(pom_data, active_profiles=["explicit"])
        assert result is pom_data
        assert "default" not in result.get("properties", {})


class TestParsePomComprehensive:
    def test_minimal(self, parser):
        pom_xml = '<project xmlns="http://maven.apache.org/POM/4.0.0"></project>'
        result = parser._parse_pom_comprehensive(pom_xml, "g", "a", "1.0")
        assert result["properties"]["project.groupId"] == "g"
        assert result["properties"]["project.artifactId"] == "a"

    def test_with_all_sections(self, parser):
        pom_xml = """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <parent>
    <groupId>parent.g</groupId>
    <artifactId>parent.a</artifactId>
    <version>1.0</version>
  </parent>
  <dependencyManagement>
    <dependencies>
      <dependency>
        <groupId>com.example</groupId>
        <artifactId>managed-lib</artifactId>
        <version>2.0</version>
      </dependency>
    </dependencies>
  </dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>com.example</groupId>
      <artifactId>my-lib</artifactId>
      <version>1.0</version>
    </dependency>
  </dependencies>
  <build>
    <pluginManagement>
      <plugins>
        <plugin>
          <groupId>org.apache.maven.plugins</groupId>
          <artifactId>maven-compiler-plugin</artifactId>
          <version>3.8.1</version>
        </plugin>
      </plugins>
    </pluginManagement>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.0.0</version>
      </plugin>
    </plugins>
  </build>
  <profiles>
    <profile>
      <id>test-profile</id>
      <properties>
        <java.version>11</java.version>
      </properties>
    </profile>
  </profiles>
</project>"""
        result = parser._parse_pom_comprehensive(
            pom_xml, "g", "a", "1.0", active_profiles=["test-profile"]
        )
        assert result["parent"]["group_id"] == "parent.g"
        assert "com.example:managed-lib" in result["dependency_management"]
        assert len(result["dependencies"]) == 1
        assert "org.apache.maven.plugins:maven-compiler-plugin" in result["plugin_management"]
        assert len(result["plugins"]) == 1
        assert "test-profile" in result["profiles"]
        assert result["properties"]["java.version"] == "11"

    def test_invalid_xml_returns_empty(self, parser):
        result = parser._parse_pom_comprehensive("not xml at all{{{", "g", "a", "1.0")
        assert result == {"dependencies": []}


class TestParseProfilesMissingId:
    def test_profile_without_id_skipped(self, parser):
        root = _pom_xml("""
            <profiles>
                <profile>
                    <properties><java.version>11</java.version></properties>
                </profile>
                <profile>
                    <id>valid</id>
                    <properties><java.version>17</java.version></properties>
                </profile>
            </profiles>
        """)
        profiles = parser._parse_profiles(root, NAMESPACES, {})
        assert "valid" in profiles
        assert len(profiles) == 1


class TestParseProfileDependencyManagement:
    def test_profile_with_dep_management(self, parser):
        root = _pom_xml("""
            <profiles>
                <profile>
                    <id>with-mgmt</id>
                    <dependencyManagement>
                        <dependencies>
                            <dependency>
                                <groupId>com.example</groupId>
                                <artifactId>managed-lib</artifactId>
                                <version>1.0</version>
                            </dependency>
                        </dependencies>
                    </dependencyManagement>
                </profile>
            </profiles>
        """)
        profiles = parser._parse_profiles(root, NAMESPACES, {})
        dm = profiles["with-mgmt"]["dependency_management"]
        assert "com.example:managed-lib" in dm
        assert dm["com.example:managed-lib"]["version"] == "1.0"


class TestExtractDependencyInfoManagement:
    def test_dep_info_management_override(self, parser):
        xml = '<dependency xmlns="http://maven.apache.org/POM/4.0.0"><groupId>com.example</groupId><artifactId>managed-dep</artifactId></dependency>'
        dep_elem = ET.fromstring(xml)
        dep_management = {"com.example:managed-dep": {"version": "2.0", "scope": "runtime"}}
        info = parser._extract_dependency_info(dep_elem, NAMESPACES, {}, dep_management)
        assert info["version"] == "2.0"


class TestExtractPluginInfo:
    def test_plugin_with_management_version(self, parser):
        xml = '<plugin xmlns="http://maven.apache.org/POM/4.0.0"><groupId>org.apache.maven.plugins</groupId><artifactId>maven-compiler-plugin</artifactId></plugin>'
        plugin_elem = ET.fromstring(xml)
        plugin_management = {"org.apache.maven.plugins:maven-compiler-plugin": {"version": "3.8.1"}}
        info = parser._extract_plugin_info(plugin_elem, NAMESPACES, {}, plugin_management)
        assert info["version"] == "3.8.1"

    def test_plugin_with_dependencies(self, parser):
        xml = """<plugin xmlns="http://maven.apache.org/POM/4.0.0">
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>3.0.0</version>
            <dependencies>
                <dependency>
                    <groupId>org.apache.maven.surefire</groupId>
                    <artifactId>surefire-api</artifactId>
                    <version>3.0.0</version>
                </dependency>
            </dependencies>
        </plugin>"""
        plugin_elem = ET.fromstring(xml)
        info = parser._extract_plugin_info(plugin_elem, NAMESPACES, {}, {})
        assert len(info["dependencies"]) == 1
        assert info["dependencies"][0]["artifact_id"] == "surefire-api"

    def test_plugin_with_nested_configuration(self, parser):
        xml = """<plugin xmlns="http://maven.apache.org/POM/4.0.0">
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.8.1</version>
            <configuration>
                <source>1.8</source>
                <compilerArgs>
                    <arg>-Xlint:all</arg>
                </compilerArgs>
            </configuration>
        </plugin>"""
        plugin_elem = ET.fromstring(xml)
        info = parser._extract_plugin_info(plugin_elem, NAMESPACES, {}, {})
        assert info["configuration"]["source"] == "1.8"
        assert info["configuration"]["compilerArgs"]["arg"] == "-Xlint:all"


class TestApplyFinalPropertySubstitution:
    def test_substitute_in_version(self, parser):
        pom_data = {
            "properties": {"revision": "1.0.0"},
            "dependencies": [
                {"group_id": "com.example", "artifact_id": "lib", "version": "${revision}"}
            ],
            "dependency_management": {},
            "repositories": [],
            "plugins": [],
            "plugin_management": {},
        }
        result = parser._apply_final_property_substitution(pom_data)
        assert result["dependencies"][0]["version"] == "1.0.0"

    def test_substitute_no_properties_match(self, parser):
        pom_data = {
            "properties": {},
            "dependencies": [{"group_id": "com.example", "artifact_id": "lib", "version": "1.0"}],
            "dependency_management": {},
            "repositories": [],
            "plugins": [],
            "plugin_management": {},
        }
        result = parser._apply_final_property_substitution(pom_data)
        assert result["dependencies"][0]["version"] == "1.0"
