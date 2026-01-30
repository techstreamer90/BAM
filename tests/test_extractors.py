"""Tests for BAM extractors."""

import json
import tempfile
from pathlib import Path

import pytest


class TestSystemVerilogExtractor:
    """Tests for the SystemVerilog extractor."""

    def test_extract_module(self):
        """Test basic module extraction."""
        from bam.extractors import SystemVerilogExtractor

        # Create a temporary file with a simple module
        sv_content = '''
        module test_module #(
            parameter WIDTH = 8
        ) (
            input  logic clk,
            input  logic rst_n,
            input  logic [WIDTH-1:0] data_in,
            output logic [WIDTH-1:0] data_out
        );
            assign data_out = data_in;
        endmodule
        '''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.sv', delete=False) as f:
            f.write(sv_content)
            temp_path = Path(f.name)

        try:
            extractor = SystemVerilogExtractor('test')
            result = extractor.extract_file(temp_path)

            assert len(result['items']) == 1
            item = result['items'][0]
            assert item['name'] == 'test_module'
            assert item['type'] == 'RTLModule'
            assert 'parameters' in item['properties']
            assert 'ports' in item['properties']
        finally:
            temp_path.unlink()

    def test_extract_package(self):
        """Test package extraction."""
        from bam.extractors import SystemVerilogExtractor

        sv_content = '''
        package my_pkg;
            typedef enum logic [1:0] {
                IDLE = 2'b00,
                RUN  = 2'b01
            } state_e;

            function automatic int add(int a, int b);
                return a + b;
            endfunction
        endpackage
        '''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.sv', delete=False) as f:
            f.write(sv_content)
            temp_path = Path(f.name)

        try:
            extractor = SystemVerilogExtractor('test')
            result = extractor.extract_file(temp_path)

            assert len(result['items']) == 1
            item = result['items'][0]
            assert item['name'] == 'my_pkg'
            assert item['type'] == 'RTLPackage'
            assert 'add' in item['properties'].get('functions', [])
        finally:
            temp_path.unlink()

    def test_extract_interface(self):
        """Test interface extraction."""
        from bam.extractors import SystemVerilogExtractor

        sv_content = '''
        interface axi_if #(
            parameter DATA_WIDTH = 32,
            parameter ADDR_WIDTH = 32
        ) (
            input logic clk
        );
            logic awvalid;
            logic awready;

            task automatic wait_clks(int n);
                repeat (n) @(posedge clk);
            endtask
        endinterface
        '''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.sv', delete=False) as f:
            f.write(sv_content)
            temp_path = Path(f.name)

        try:
            extractor = SystemVerilogExtractor('test')
            result = extractor.extract_file(temp_path)

            assert len(result['items']) == 1
            item = result['items'][0]
            assert item['name'] == 'axi_if'
            assert item['type'] == 'RTLInterface'
            assert 'wait_clks' in item['properties'].get('tasks', [])
        finally:
            temp_path.unlink()

    def test_extract_class(self):
        """Test class extraction with inheritance."""
        from bam.extractors import SystemVerilogExtractor

        sv_content = '''
        class my_driver extends uvm_driver;
            function new(string name, uvm_component parent);
                super.new(name, parent);
            endfunction

            virtual task run_phase(uvm_phase phase);
                // Drive signals
            endtask
        endclass
        '''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.sv', delete=False) as f:
            f.write(sv_content)
            temp_path = Path(f.name)

        try:
            extractor = SystemVerilogExtractor('test')
            result = extractor.extract_file(temp_path)

            assert len(result['items']) == 1
            item = result['items'][0]
            assert item['name'] == 'my_driver'
            assert item['type'] == 'VerificationClass'
            assert item['properties'].get('extends') == 'uvm_driver'

            # Check inheritance relationship
            assert len(result['relationships']) == 1
            rel = result['relationships'][0]
            assert rel['type'] == 'EXTENDS'
            assert rel['source'] == 'my_driver'
            assert rel['target'] == 'uvm_driver'
        finally:
            temp_path.unlink()

    def test_extract_instantiation(self):
        """Test module instantiation detection."""
        from bam.extractors import SystemVerilogExtractor

        sv_content = '''
        module top_module (
            input  logic clk,
            input  logic rst_n
        );
            // Instantiation with parameters
            child_module #(
                .WIDTH(8),
                .DEPTH(16)
            ) u_child (
                .clk(clk),
                .rst_n(rst_n)
            );

            // Simple instantiation
            another_module u_another (
                .clk(clk)
            );
        endmodule
        '''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.sv', delete=False) as f:
            f.write(sv_content)
            temp_path = Path(f.name)

        try:
            extractor = SystemVerilogExtractor('test')
            result = extractor.extract_file(temp_path)

            # Check instantiation relationships
            inst_rels = [r for r in result['relationships'] if r['type'] == 'INSTANTIATES']
            assert len(inst_rels) == 2

            targets = {r['target'] for r in inst_rels}
            assert 'child_module' in targets
            assert 'another_module' in targets
        finally:
            temp_path.unlink()

    def test_extract_import(self):
        """Test import detection."""
        from bam.extractors import SystemVerilogExtractor

        sv_content = '''
        module importer;
            import my_pkg::*;
            import other_pkg::some_type;
        endmodule
        '''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.sv', delete=False) as f:
            f.write(sv_content)
            temp_path = Path(f.name)

        try:
            extractor = SystemVerilogExtractor('test')
            result = extractor.extract_file(temp_path)

            item = result['items'][0]
            imports = item['properties'].get('imports', [])
            assert 'my_pkg::*' in imports
            assert 'other_pkg::some_type' in imports

            # Check import relationships
            import_rels = [r for r in result['relationships'] if r['type'] == 'IMPORTS']
            targets = {r['target'] for r in import_rels}
            assert 'my_pkg' in targets
            assert 'other_pkg' in targets
        finally:
            temp_path.unlink()

    def test_extract_directory(self, tmp_path):
        """Test directory extraction."""
        from bam.extractors import SystemVerilogExtractor

        # Create test files
        (tmp_path / 'mod_a.sv').write_text('''
            module mod_a;
            endmodule
        ''')
        (tmp_path / 'mod_b.sv').write_text('''
            module mod_b;
                mod_a u_a ();
            endmodule
        ''')
        (tmp_path / 'sub').mkdir()
        (tmp_path / 'sub' / 'mod_c.sv').write_text('''
            module mod_c;
            endmodule
        ''')

        extractor = SystemVerilogExtractor('test')
        result = extractor.extract_directory(tmp_path, recursive=True)

        assert result.success
        assert result.file_count == 3
        assert result.item_count == 3

        names = {item['name'] for item in result.items}
        assert names == {'mod_a', 'mod_b', 'mod_c'}

    def test_to_bam_format(self, tmp_path):
        """Test conversion to BAM ingestion format."""
        from bam.extractors import SystemVerilogExtractor

        (tmp_path / 'test.sv').write_text('''
            module test_mod;
            endmodule
        ''')

        extractor = SystemVerilogExtractor('my-source')
        result = extractor.extract_directory(tmp_path)
        bam_data = extractor.to_bam_format(result)

        assert bam_data['source'] == 'my-source'
        assert bam_data['extractor'] == 'systemverilog'
        assert 'fetchedAt' in bam_data
        assert len(bam_data['items']) == 1
        assert bam_data['items'][0]['name'] == 'test_mod'

    def test_classification_rtl_vs_verification(self, tmp_path):
        """Test automatic classification of RTL vs verification code."""
        from bam.extractors import SystemVerilogExtractor

        # Create RTL-like structure
        rtl_dir = tmp_path / 'rtl'
        rtl_dir.mkdir()
        (rtl_dir / 'my_module.sv').write_text('''
            module my_module;
            endmodule
        ''')

        # Create verification-like structure
        dv_dir = tmp_path / 'dv'
        dv_dir.mkdir()
        (dv_dir / 'my_driver.sv').write_text('''
            class my_driver extends uvm_driver;
            endclass
        ''')

        extractor = SystemVerilogExtractor('test')
        result = extractor.extract_directory(tmp_path, recursive=True)
        bam_data = extractor.to_bam_format(result)

        # Find items by name
        items_by_name = {item['name']: item for item in bam_data['items']}

        # Check classifications
        assert items_by_name['my_module']['category'] == 'rtl'
        assert items_by_name['my_driver']['category'] == 'verification'
        assert items_by_name['my_driver']['role'] == 'driver'

    def test_uvm_role_detection(self):
        """Test detection of various UVM component roles."""
        from bam.extractors import SystemVerilogExtractor
        import tempfile

        sv_content = '''
            class my_test extends uvm_test;
            endclass

            class my_env extends uvm_env;
            endclass

            class my_agent extends uvm_agent;
            endclass

            class my_scoreboard extends uvm_scoreboard;
            endclass

            class my_seq extends uvm_sequence;
            endclass
        '''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.sv', delete=False) as f:
            f.write(sv_content)
            temp_path = Path(f.name)

        try:
            extractor = SystemVerilogExtractor('test')
            result = extractor.extract_file(temp_path)

            roles = {item['name']: item.get('role') for item in result['items']}

            assert roles['my_test'] == 'test'
            assert roles['my_env'] == 'env'
            assert roles['my_agent'] == 'agent'
            assert roles['my_scoreboard'] == 'scoreboard'
            assert roles['my_seq'] == 'sequence'
        finally:
            temp_path.unlink()

    def test_summary_generation(self, tmp_path):
        """Test that summary provides useful overview for agents."""
        from bam.extractors import SystemVerilogExtractor

        # Create a mini project structure
        (tmp_path / 'top.sv').write_text('''
            module top;
                child u_child();
            endmodule
        ''')
        (tmp_path / 'child.sv').write_text('''
            module child;
            endmodule
        ''')

        extractor = SystemVerilogExtractor('test')
        result = extractor.extract_directory(tmp_path)
        bam_data = extractor.to_bam_format(result)

        summary = bam_data['summary']

        assert summary['total_items'] == 2
        assert summary['by_type']['RTLModule'] == 2
        # 'top' is top-level (not instantiated), 'child' is instantiated
        assert 'top' in summary['top_level_modules']
        assert 'child' not in summary['top_level_modules']
