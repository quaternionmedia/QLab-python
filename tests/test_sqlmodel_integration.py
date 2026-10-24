#!/usr/bin/env python3
"""Integration tests for SQLModel-based database module."""

import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from qlab.database_sqlmodel import CueDatabase
from qlab.models import Cue, Profile, Config


def test_basic_operations():
    """Test basic database operations."""
    print("Testing basic database operations...")
    
    db_path = "test_sqlmodel_integration.sqlite"
    
    try:
        with CueDatabase(db_path) as db:
            # Test cue creation
            point1 = db.add_cue(name="Test Cue 1", colour=5)
            assert point1 == 10, f"Expected point 10, got {point1}"
            
            point2 = db.add_unmute_cue("Character A", "1", "Test line")
            assert point2 == 20, f"Expected point 20, got {point2}"
            
            point3 = db.add_mute_cue("Character A", "1", "End line")
            assert point3 == 30, f"Expected point 30, got {point3}"
            
            # Test retrieval - returns Cue object
            cue = db.get_cue(point1)
            assert cue is not None
            assert cue.name == "Test Cue 1"
            assert cue.colour == 5
            
            # Test update
            db.update_cue(point1, name="Updated Cue 1", colour=7)
            cue = db.get_cue(point1)
            assert cue.name == "Updated Cue 1"
            assert cue.colour == 7
            
            # Test get all
            all_cues = db.get_all_cues()
            assert len(all_cues) == 3
            assert isinstance(all_cues[0], Cue)
            
        print("✓ Basic operations test passed")
        return True
        
    finally:
        # Cleanup
        Path(db_path).unlink(missing_ok=True)


def test_config_operations():
    """Test configuration operations."""
    print("Testing configuration operations...")
    
    db_path = "test_sqlmodel_config.sqlite"
    
    try:
        with CueDatabase(db_path, init_config=True) as db:
            # Test default config was initialized
            designer = db.get_config("designer")
            assert designer == "Copilot", f"Expected 'Copilot', got {designer}"
            
            # Test setting config
            db.set_config("designer", "TestUser")
            designer = db.get_config("designer")
            assert designer == "TestUser", f"Expected 'TestUser', got {designer}"
            
            # Test get all config
            all_config = db.get_all_config()
            assert isinstance(all_config, dict)
            assert "targetConsole" in all_config
            assert len(all_config) > 10  # Should have many config entries
            
        print("✓ Configuration operations test passed")
        return True
        
    finally:
        Path(db_path).unlink(missing_ok=True)


def test_character_profiles():
    """Test character profile integration."""
    print("Testing character profile integration...")
    
    # Use the example database which has profiles
    db_path = Path(__file__).parent.parent / "mix" / "SheKillsMonsters.sqlite"
    
    if not db_path.exists():
        print("⚠ Skipping - example database not found")
        return True
    
    with CueDatabase(str(db_path), create_schema=False, init_config=False) as db:
        # Get profiles - returns Profile objects
        profiles = db.get_profiles()
        assert len(profiles) > 0, "No profiles found"
        assert isinstance(profiles[0], Profile)
        
        # Get channel for known character
        channel = db.get_channel_for_character("Agnes")
        assert channel == 1, f"Expected channel 1, got {channel}"
        
        # Test adding cue with profile lookup
        start_point = db.get_next_cue_number()[1]
        point = db.add_unmute_cue(
            "Tilly",
            channels=str(db.get_channel_for_character("Tilly") or ""),
            line_preview="Test line",
            dca=1,
        )
        
        # Verify and cleanup
        cue = db.get_cue(point)
        assert cue is not None
        assert "Tilly" in cue.name
        db.delete_cue(point)
    
    print("✓ Character profile test passed")
    return True


def test_dca_assignments():
    """Test DCA channel assignments."""
    print("Testing DCA assignments...")
    
    db_path = "test_sqlmodel_dca.sqlite"
    
    try:
        with CueDatabase(db_path) as db:
            # Add cue with multiple DCA assignments
            point = db.add_cue(
                name="Multi-DCA Test",
                dca_channels={
                    1: "1,2,3",
                    2: "4,5",
                    8: "8",
                    12: "11,12",
                },
                dca_labels={
                    1: "Group A",
                    2: "Group B",
                },
            )
            
            # Verify DCA assignments - returns Cue object
            cue = db.get_cue(point)
            assert cue is not None
            assert cue.dca01Channels == "1,2,3"
            assert cue.dca02Channels == "4,5"
            assert cue.dca08Channels == "8"
            assert cue.dca12Channels == "11,12"
            assert cue.dca01Label == "Group A"
            assert cue.dca02Label == "Group B"
            
        print("✓ DCA assignments test passed")
        return True
        
    finally:
        Path(db_path).unlink(missing_ok=True)


def test_sqlmodel_features():
    """Test SQLModel-specific features."""
    print("Testing SQLModel-specific features...")
    
    db_path = "test_sqlmodel_features.sqlite"
    
    try:
        with CueDatabase(db_path) as db:
            # Create cue
            point = db.add_cue(name="Test", colour=5)
            
            # Get cue as SQLModel object
            cue = db.get_cue(point)
            assert isinstance(cue, Cue)
            
            # Test model dict conversion
            cue_dict = cue.model_dump()
            assert isinstance(cue_dict, dict)
            assert cue_dict['name'] == "Test"
            assert cue_dict['point'] == point
            
            # Test model validation
            assert cue.point == point
            assert cue.name == "Test"
            
        print("✓ SQLModel features test passed")
        return True
        
    finally:
        Path(db_path).unlink(missing_ok=True)


def main():
    """Run all integration tests."""
    print("=" * 60)
    print("QLab-python SQLModel Database Integration Tests")
    print("=" * 60)
    print()
    
    tests = [
        test_basic_operations,
        test_config_operations,
        test_character_profiles,
        test_dca_assignments,
        test_sqlmodel_features,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"✗ {test.__name__} failed: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
        print()
    
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
